"""Claude Code oturum kayıtlarını okuyan kaynak.

Claude Code her oturumu `~/.claude/projects/<kodlanmış-dizin>/<oturum>.jsonl`
altında satır satır JSON olarak tutar. Bu dosyada konuşmanın yanında araç
çağrıları, araç çıktıları ve düşünme blokları da bulunur; seslendirmek
istediğimiz yalnızca gerçek konuşmadır.

Okunan:      asistanın `text` blokları, kullanıcının düz metin mesajları
Atlanan:     `thinking`, `tool_use`, `tool_result`, sistem kayıtları,
             alt ajan (sidechain) konuşmaları
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..i18n import _

TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"

_ROLE_LABELS = {"user": "Kullanıcı", "assistant": "Asistan"}
"""Birden çok rol seslendirilirken araya konan sesli ayraçlar."""

# Kullanıcı mesajlarına araç tarafından eklenen, konuşmaya ait olmayan bloklar.
_TAG_BLOCK_RE = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout)>"
    r".*?</\1>",
    re.DOTALL,
)


class TranscriptError(RuntimeError):
    """Transkript bulunamadığında veya okunamadığında oluşan hata."""


class Roles(str, Enum):
    """Hangi konuşmacıların seslendirileceği."""

    ASSISTANT = "assistant"
    USER = "user"
    ALL = "all"

    def matches(self, role: str) -> bool:
        return self is Roles.ALL or self.value == role


@dataclass(frozen=True)
class Turn:
    """Konuşmadaki tek bir söz sırası."""

    role: str
    text: str


def session_dir(cwd: Path) -> Path:
    """Bir çalışma dizinine karşılık gelen transkript klasörü.

    Claude Code, yoldaki harf ve rakam dışındaki her karakteri tireye
    çevirerek klasör adını üretir.
    """
    return TRANSCRIPT_ROOT / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def find_sessions(cwd: Path) -> list[Path]:
    """Bir projenin oturum dosyalarını, en yeni başta olacak şekilde döner."""
    directory = session_dir(cwd)
    if not directory.is_dir():
        return []
    sessions = [path for path in directory.glob("*.jsonl") if path.is_file()]
    return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)


def latest_session(cwd: Path) -> Path:
    """Projenin en son güncellenmiş oturum dosyası."""
    sessions = find_sessions(cwd)
    if not sessions:
        raise TranscriptError(
            _(
                "{cwd} için Claude Code oturum kaydı bulunamadı "
                "(bakılan yer: {looked})"
            ).format(cwd=cwd, looked=session_dir(cwd))
        )
    return sessions[0]


def read_turns(path: Path) -> list[Turn]:
    """Oturum dosyasındaki konuşmayı mantıksal söz sıraları olarak döner.

    Tek bir cevap, araya giren araç çağrıları yüzünden onlarca kayda
    bölünebilir. Kullanıcı açısından bunların tamamı tek bir yanıttır; bu
    yüzden ardışık aynı rolden kayıtlar tek söz sırasında birleştirilir.

    Bozuk satırlar sessizce atlanır: kayıt dosyası yazılırken okunabilir ve
    son satır yarım kalmış olabilir.
    """
    return _merge_consecutive(_read_records(path))


def _read_records(path: Path) -> list[Turn]:
    """Dosyadaki her konuşma kaydını ayrı ayrı döner (birleştirmeden)."""
    turns: list[Turn] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = _parse_line(line)
            if record is None:
                continue
            turn = _to_turn(record)
            if turn is not None:
                turns.append(turn)
    return turns


def _merge_consecutive(turns: list[Turn]) -> list[Turn]:
    """Ardışık aynı rolden söz sıralarını tek parçada toplar."""
    merged: list[Turn] = []
    for turn in turns:
        if merged and merged[-1].role == turn.role:
            combined_text = f"{merged[-1].text}\n\n{turn.text}"
            merged[-1] = Turn(role=turn.role, text=combined_text)
            continue
        merged.append(turn)
    return merged


def collect(path: Path, last: int | None = 1, roles: Roles = Roles.ASSISTANT) -> str:
    """Seçilen rollerin son `last` söz sırasını seslendirilecek metne çevirir.

    `last` None ise konuşmanın tamamı alınır. Birden çok rol seçildiğinde
    araya kimin konuştuğunu belirten kısa bir ayraç konur.
    """
    selected = [turn for turn in read_turns(path) if roles.matches(turn.role)]
    if last is not None:
        if last < 1:
            raise ValueError(_("last en az 1 olmalı"))
        selected = selected[-last:]

    if not selected:
        return ""

    if roles is not Roles.ALL:
        return "\n\n".join(turn.text for turn in selected)

    return "\n\n".join(
        f"{_ROLE_LABELS.get(turn.role, turn.role)}: {turn.text}" for turn in selected
    )


def _parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def _to_turn(record: dict) -> Turn | None:
    """Tek bir kaydı söz sırasına çevirir; konuşma değilse None döner."""
    role = record.get("type")
    if role not in ("user", "assistant"):
        return None
    # Alt ajan konuşmaları kullanıcıya dönen cevap değildir.
    if record.get("isSidechain"):
        return None

    message = record.get("message")
    if not isinstance(message, dict):
        return None

    text = _extract_text(message.get("content"), role)
    return Turn(role=role, text=text) if text else None


def _extract_text(content: object, role: str) -> str:
    """Mesaj içeriğinden yalnızca konuşulan metni çıkarır."""
    if isinstance(content, str):
        return _clean(content)

    if not isinstance(content, list):
        return ""

    # Araç çıktısı ve düşünme blokları konuşma değildir; yalnızca metin alınır.
    pieces = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return _clean("\n\n".join(piece for piece in pieces if piece.strip()))


def _clean(text: str) -> str:
    """Konuşmaya ait olmayan araç etiketlerini metinden temizler."""
    return _TAG_BLOCK_RE.sub("", text).strip()
