"""Markdown metnini blok seviyesinde `Segment`'lere ayırır.

Burada bilinçli olarak yalnızca **blok** yapılar tanınır (kod bloğu, tablo,
başlık, liste, alıntı, yatay çizgi). Satır içi öğeler (`kod`, URL) düz metnin
akışını bozmamak için ayrı segment yapılmaz; onları `policy` katmanı cümlenin
içinde yerinde dönüştürür.

Tam bir Markdown uyumluluğu hedeflenmez — amaç, seslendirme kararı vermeye
yetecek kadar doğru bir sınıflandırmadır.
"""

from __future__ import annotations

import re

from ..models import Segment, SegmentType

_FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>\S*)")
_HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$")
_HR_RE = re.compile(r"^ {0,3}(?:-\s*){3,}$|^ {0,3}(?:\*\s*){3,}$|^ {0,3}(?:_\s*){3,}$")
_QUOTE_RE = re.compile(r"^ {0,3}>\s?(?P<text>.*)$")
_BULLET_RE = re.compile(r"^(?P<indent> *)(?P<marker>[-*+]|\d{1,9}[.)])\s+(?P<text>.*)$")
_TABLE_DELIM_RE = re.compile(r"^ {0,3}\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")


def parse_segments(text: str) -> list[Segment]:
    """Ham metni sırasıyla `Segment` listesine çevirir.

    Segmentler kaynaktaki sırayı korur; hiçbir içerik burada elenmez.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[Segment] = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        for reader in (
            _read_fenced_code,
            _read_heading,
            _read_horizontal_rule,
            _read_table,
            _read_quote,
            _read_list_item,
            _read_indented_code,
        ):
            result = reader(lines, index)
            if result is not None:
                segment, index = result
                segments.append(segment)
                break
        else:
            segment, index = _read_paragraph(lines, index)
            segments.append(segment)

    return segments


def _read_fenced_code(
    lines: list[str], start: int
) -> tuple[Segment, int] | None:
    """```dil ... ``` bloğunu okur. Kapanmayan çit dosya sonuna kadar sürer."""
    match = _FENCE_RE.match(lines[start])
    if match is None:
        return None

    fence = match.group("fence")
    fence_char = fence[0]
    closing = re.compile(rf"^ {{0,3}}{re.escape(fence_char)}{{{len(fence)},}}\s*$")

    body: list[str] = []
    cursor = start + 1
    while cursor < len(lines) and not closing.match(lines[cursor]):
        body.append(lines[cursor])
        cursor += 1

    # Kapanış çiti varsa onu da tüket; yoksa zaten dosya sonundayız.
    end = cursor + 1 if cursor < len(lines) else cursor

    info = match.group("info")
    return (
        Segment(
            type=SegmentType.CODE_BLOCK,
            text="\n".join(body),
            line_count=len(body),
            language=info or None,
        ),
        end,
    )


def _read_heading(lines: list[str], start: int) -> tuple[Segment, int] | None:
    """ATX başlığını (`## Başlık`) okur."""
    match = _HEADING_RE.match(lines[start])
    if match is None:
        return None

    return (
        Segment(
            type=SegmentType.HEADING,
            text=match.group("text").strip(),
            line_count=1,
            level=len(match.group("hashes")),
        ),
        start + 1,
    )


def _read_horizontal_rule(
    lines: list[str], start: int
) -> tuple[Segment, int] | None:
    if not _HR_RE.match(lines[start]):
        return None
    return (
        Segment(type=SegmentType.HORIZONTAL_RULE, text=lines[start].strip()),
        start + 1,
    )


def _read_table(lines: list[str], start: int) -> tuple[Segment, int] | None:
    """Markdown tablosunu okur.

    Tablo, ikinci satırındaki ayraç satırından (`|---|---|`) tanınır; bu, düz
    metinde geçen tek tük `|` karakterinin tablo sanılmasını engeller.
    """
    if "|" not in lines[start]:
        return None
    if start + 1 >= len(lines) or not _TABLE_DELIM_RE.match(lines[start + 1]):
        return None

    body: list[str] = []
    cursor = start
    while cursor < len(lines) and "|" in lines[cursor] and lines[cursor].strip():
        body.append(lines[cursor])
        cursor += 1

    # Anonsta "kaç satır" derken kastedilen veri satırlarıdır; başlık ve
    # ayraç satırı içerik taşımaz.
    row_count = max(len(body) - 2, 0)
    return (
        Segment(
            type=SegmentType.TABLE,
            text="\n".join(body),
            line_count=row_count,
        ),
        cursor,
    )


def _read_quote(lines: list[str], start: int) -> tuple[Segment, int] | None:
    """Ardışık `>` satırlarını tek bir alıntı segmenti olarak okur."""
    match = _QUOTE_RE.match(lines[start])
    if match is None:
        return None

    body: list[str] = []
    cursor = start
    while cursor < len(lines):
        line_match = _QUOTE_RE.match(lines[cursor])
        if line_match is None:
            break
        body.append(line_match.group("text"))
        cursor += 1

    return (
        Segment(
            type=SegmentType.QUOTE,
            text="\n".join(body).strip(),
            line_count=len(body),
        ),
        cursor,
    )


def _read_list_item(lines: list[str], start: int) -> tuple[Segment, int] | None:
    """Tek bir liste maddesini, girintili devam satırlarıyla birlikte okur.

    Her madde ayrı segmenttir; böylece maddeler arasında doğal bir duraklama
    oluşur ve uzun listeler chunk sınırlarında güvenle bölünebilir.
    """
    match = _BULLET_RE.match(lines[start])
    if match is None:
        return None

    indent = len(match.group("indent"))
    body = [match.group("text")]
    cursor = start + 1

    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            break
        if _BULLET_RE.match(line):
            break
        if len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line.strip())
        cursor += 1

    return (
        Segment(
            type=SegmentType.LIST_ITEM,
            text=" ".join(part for part in body if part),
            line_count=len(body),
        ),
        cursor,
    )


def _read_indented_code(
    lines: list[str], start: int
) -> tuple[Segment, int] | None:
    """Girintili (4 boşluk / tab) kod bloğunu okur.

    Yalnızca boş satırdan sonra gelen girintiler kod sayılır; aksi hâlde liste
    maddelerinin devam satırları yanlışlıkla kod olarak işaretlenirdi.
    """
    if not _INDENTED_CODE_RE.match(lines[start]):
        return None
    if start > 0 and lines[start - 1].strip():
        return None

    body: list[str] = []
    cursor = start
    while cursor < len(lines):
        line = lines[cursor]
        if line.strip() and not _INDENTED_CODE_RE.match(line):
            break
        body.append(line)
        cursor += 1

    while body and not body[-1].strip():
        body.pop()
        cursor -= 1

    return (
        Segment(
            type=SegmentType.CODE_BLOCK,
            text="\n".join(body),
            line_count=len(body),
        ),
        cursor,
    )


def _read_paragraph(lines: list[str], start: int) -> tuple[Segment, int]:
    """Boş satıra veya başka bir blok başlangıcına kadar düz metni toplar."""
    body: list[str] = []
    cursor = start

    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            break
        if cursor > start and _starts_new_block(lines, cursor):
            break
        body.append(line.strip())
        cursor += 1

    return (
        Segment(
            type=SegmentType.PROSE,
            text=" ".join(body),
            line_count=len(body),
        ),
        cursor,
    )


def _starts_new_block(lines: list[str], index: int) -> bool:
    """Paragrafın ortasında yeni bir blok yapısının başlayıp başlamadığı."""
    line = lines[index]
    if _FENCE_RE.match(line) or _HEADING_RE.match(line):
        return True
    if _HR_RE.match(line) or _QUOTE_RE.match(line) or _BULLET_RE.match(line):
        return True
    return (
        "|" in line
        and index + 1 < len(lines)
        and bool(_TABLE_DELIM_RE.match(lines[index + 1]))
    )
