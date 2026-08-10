"""Pano içeriğini okuyan kaynak.

Linux'ta panoyu okumanın tek bir yolu yok: X11'de `xclip`/`xsel`, Wayland'de
`wl-paste` kullanılır. Oturum tipine göre en uygun aracı seçer, yoksa
kurulanların arasından ilerler.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


class ClipboardError(RuntimeError):
    """Pano okunamadığında oluşan, kullanıcıya gösterilebilir hata."""


@dataclass(frozen=True)
class _Reader:
    """Panoyu okuyan tek bir harici araç."""

    binary: str
    args: tuple[str, ...]
    session: str | None
    """Tercih edildiği oturum tipi ("wayland"/"x11"); None ise fark etmez."""

    def command(self) -> list[str]:
        return [self.binary, *self.args]


_READERS = (
    _Reader("wl-paste", ("--no-newline",), session="wayland"),
    _Reader("xclip", ("-o", "-selection", "clipboard"), session="x11"),
    _Reader("xsel", ("--clipboard", "--output"), session="x11"),
)

_INSTALL_HINT = (
    "Pano okunamıyor: xclip, xsel veya wl-clipboard kurulu değil. "
    "Kurmak için: sudo apt install xclip"
)


def read_clipboard() -> str:
    """Pano içeriğini metin olarak döner.

    Pano boşsa boş dizge döner; okuma aracı hiç yoksa `ClipboardError` fırlatır.
    """
    readers = _available_readers()
    if not readers:
        raise ClipboardError(_INSTALL_HINT)

    errors: list[str] = []
    for reader in readers:
        try:
            return _read_with(reader)
        except ClipboardError as exc:
            errors.append(f"{reader.binary}: {exc}")

    raise ClipboardError("Pano okunamadı — " + "; ".join(errors))


def _available_readers() -> list[_Reader]:
    """Kurulu okuyucuları, oturum tipine uygun olan başta olacak şekilde sıralar."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    kurulu = [reader for reader in _READERS if shutil.which(reader.binary)]
    return sorted(kurulu, key=lambda reader: reader.session != session)


def _read_with(reader: _Reader) -> str:
    try:
        result = subprocess.run(
            reader.command(), capture_output=True, text=True, timeout=5
        )
    except OSError as exc:
        raise ClipboardError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError("araç yanıt vermedi") from exc

    if result.returncode != 0:
        # Boş pano da hata koduyla döner; bunu içerik yokluğu sayarız.
        stderr = result.stderr.strip()
        if _bos_pano_hatasi(stderr):
            return ""
        raise ClipboardError(stderr or f"çıkış kodu {result.returncode}")

    return result.stdout


def _bos_pano_hatasi(stderr: str) -> bool:
    """Araçların "pano boş" anlamına gelen hata metinlerini tanır."""
    dusuk = stderr.lower()
    return "target string not available" in dusuk or "no selection" in dusuk
