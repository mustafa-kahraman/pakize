"""Segmentlere politika uygulayıp seslendirilebilir metin üretir.

İki iş yapar:
1. **Blok politikası** — her `Segment` tipine config'teki `Action` uygulanır
   (oku / anons et / atla).
2. **Satır içi normalizasyon** — okunacak metinden Markdown işaretleri
   temizlenir, satır içi kod ve bağlantılar yine politikaya göre yerinde
   dönüştürülür.
"""

from __future__ import annotations

import re

from ..config import Config
from ..models import Action, Segment, SegmentType

_MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<url>[^)]*)\)")
_INLINE_CODE_RE = re.compile(r"`+(?P<code>[^`]+)`+")
_BARE_URL_RE = re.compile(r"<?\b(?:https?://|www\.)[^\s<>()\[\]]+>?")
_EMPHASIS_RE = re.compile(r"(\*{1,3}|~{2})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
# Alt çizgili vurgu yalnızca kelime sınırlarında geçerlidir; aksi hâlde
# `build_chunks` gibi snake_case tanımlayıcılar parçalanırdı.
_UNDERSCORE_EMPHASIS_RE = re.compile(
    r"(?<![\w])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?![\w])", re.DOTALL
)
_LEFTOVER_MARKS_RE = re.compile(r"[*~]{1,3}")
_WHITESPACE_RE = re.compile(r"\s+")

_LANGUAGE_NAMES = {
    "bash": "Bash",
    "c": "C",
    "cpp": "C++",
    "cs": "C sharp",
    "css": "CSS",
    "go": "Go",
    "html": "HTML",
    "java": "Java",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "json": "JSON",
    "jsx": "JavaScript",
    "kt": "Kotlin",
    "php": "PHP",
    "py": "Python",
    "python": "Python",
    "rb": "Ruby",
    "rs": "Rust",
    "rust": "Rust",
    "sh": "Bash",
    "shell": "Bash",
    "sql": "SQL",
    "swift": "Swift",
    "toml": "TOML",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "tsx": "TypeScript",
    "vue": "Vue",
    "yaml": "YAML",
    "yml": "YAML",
}

_INLINE_ANNOUNCEMENTS = {
    SegmentType.INLINE_CODE: "bir kod parçası",
    SegmentType.URL: "bir bağlantı",
}


def apply_policy(
    segments: list[Segment], config: Config
) -> tuple[list[str], dict[SegmentType, int]]:
    """Segmentleri seslendirilecek metin parçalarına çevirir.

    Dönen listedeki her eleman kendi başına anlamlı bir söyleyiştir; hangi
    tipten kaç segmentin atlandığı ikinci değerde raporlanır.
    """
    utterances: list[str] = []
    skipped: dict[SegmentType, int] = {}

    for segment in segments:
        action = config.policy.get(segment.type, Action.READ)

        if action is Action.SKIP:
            _tally(skipped, segment.type, 1)
            continue

        if action is Action.ANNOUNCE:
            _tally(skipped, segment.type, 1)
            utterances.append(_announce(segment))
            continue

        spoken, inline_skipped = _render(segment, config)
        for segment_type, count in inline_skipped.items():
            _tally(skipped, segment_type, count)
        if spoken:
            utterances.append(spoken)

    return utterances, skipped


def _tally(counter: dict[SegmentType, int], key: SegmentType, amount: int) -> None:
    if amount:
        counter[key] = counter.get(key, 0) + amount


def _announce(segment: Segment) -> str:
    """Okunmayan bir bloğun yerine geçecek kısa Türkçe anons cümlesi."""
    if segment.type is SegmentType.CODE_BLOCK:
        language = _language_name(segment.language)
        subject = f"{language} kod bloğu" if language else "kod bloğu"
        return f"Burada {segment.line_count} satırlık bir {subject} var."

    if segment.type is SegmentType.TABLE:
        return f"Burada {segment.line_count} satırlık bir tablo var."

    return "Burada okunmayan bir bölüm var."


def _language_name(language: str | None) -> str | None:
    """Kod bloğu dil etiketini okunabilir bir isme çevirir."""
    if not language:
        return None
    return _LANGUAGE_NAMES.get(language.lower(), language)


def _render(
    segment: Segment, config: Config
) -> tuple[str, dict[SegmentType, int]]:
    """Okunacak bir segmenti seslendirmeye hazır metne çevirir.

    İkinci değer, satır içinde okunmadan geçilen öğelerin sayımıdır; blok
    seviyesindeki atlamalarla aynı rapora girer.
    """
    if segment.type is SegmentType.CODE_BLOCK:
        # Politika "oku" ise kodu ham hâliyle veririz; normalizasyon kodu bozar.
        return segment.text.strip(), {}

    text, skipped = _normalize_inline(segment.text, config)
    if not text:
        return "", skipped

    # Başlık ve liste maddeleri çoğu zaman noktalamasız biter; nokta eklemek
    # TTS'in araya doğal bir duraklama koymasını sağlar.
    if segment.type in (SegmentType.HEADING, SegmentType.LIST_ITEM):
        if text[-1] not in ".!?:;,":
            text += "."

    return text, skipped


def _normalize_inline(
    text: str, config: Config
) -> tuple[str, dict[SegmentType, int]]:
    """Satır içi Markdown işaretlerini politikaya göre temizler/dönüştürür."""
    text = _MD_IMAGE_RE.sub(lambda m: m.group("alt"), text)
    text = _MD_LINK_RE.sub(lambda m: m.group("text"), text)

    skipped: dict[SegmentType, int] = {}

    text, count = _substitute_inline(
        _INLINE_CODE_RE,
        text,
        config.policy.get(SegmentType.INLINE_CODE, Action.READ),
        SegmentType.INLINE_CODE,
        lambda m: m.group("code"),
    )
    _tally(skipped, SegmentType.INLINE_CODE, count)

    text, count = _substitute_inline(
        _BARE_URL_RE,
        text,
        config.policy.get(SegmentType.URL, Action.SKIP),
        SegmentType.URL,
        lambda m: m.group(0).strip("<>"),
    )
    _tally(skipped, SegmentType.URL, count)

    text = _EMPHASIS_RE.sub(lambda m: m.group(2), text)
    text = _UNDERSCORE_EMPHASIS_RE.sub(lambda m: m.group(2), text)
    text = _LEFTOVER_MARKS_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip(), skipped


def _substitute_inline(
    pattern: re.Pattern[str],
    text: str,
    action: Action,
    segment_type: SegmentType,
    read_value,
) -> tuple[str, int]:
    """Satır içi bir örüntüyü politikaya göre okur, anons eder veya siler.

    Dönen sayı, okunmadan geçilen eşleşme adedidir (READ ise sıfır).
    """
    if action is Action.READ:
        return pattern.sub(read_value, text), 0

    replacement = (
        _INLINE_ANNOUNCEMENTS[segment_type] if action is Action.ANNOUNCE else ""
    )
    result, count = pattern.subn(replacement, text)
    return result, count
