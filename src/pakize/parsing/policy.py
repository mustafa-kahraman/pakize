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
from ..i18n import in_language, voice_language
from ..models import Action, Segment, SegmentType
from .text import normalize_decimals

_MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<url>[^)]*)\)")
_INLINE_CODE_RE = re.compile(r"`+(?P<code>[^`]+)`+")
_BARE_URL_RE = re.compile(r"<?\b(?:https?://|www\.)[^\s<>()\[\]]+>?")
# Dosya yolu: en az bir eğik çizgi içeren ve son bileşeni uzantılı olan dizi.
# Uzantı şartı "ve/veya", "TR/EN" gibi ifadelerin yol sanılmasını; öndeki
# lookbehind ise URL'lerin içinden parça kapılmasını önler.
_FILE_PATH_RE = re.compile(
    r"(?<![\w/.])[\w.~-]*(?:/[\w.-]+)*/(?P<name>[\w-]+\.[A-Za-z]\w{0,7})(?![\w/])"
)
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
    SegmentType.FILE_PATH: "bir dosya yolu",
}
"""Satır içi anonsların Türkçe kaynak metinleri; `in_language` ile çevrilir."""


def apply_policy(
    segments: list[Segment], config: Config
) -> tuple[list[str], dict[SegmentType, int]]:
    """Segmentleri seslendirilecek metin parçalarına çevirir.

    Dönen listedeki her eleman kendi başına anlamlı bir söyleyiştir; hangi
    tipten kaç segmentin atlandığı ikinci değerde raporlanır.
    """
    # Anonslar seslendirilecek metnin parçası; bu yüzden arayüz diline değil
    # okunan sesin diline uyarlar.
    lang = voice_language(config.voice)

    utterances: list[str] = []
    skipped: dict[SegmentType, int] = {}

    for segment in segments:
        action = config.policy.get(segment.type, Action.READ)

        if action is Action.SKIP:
            _tally(skipped, segment.type, 1)
            continue

        if action is Action.ANNOUNCE:
            _tally(skipped, segment.type, 1)
            utterances.append(_announce(segment, lang))
            continue

        spoken, inline_skipped = _render(segment, config, lang)
        for segment_type, count in inline_skipped.items():
            _tally(skipped, segment_type, count)
        if spoken:
            utterances.append(spoken)

    return utterances, skipped


def _tally(counter: dict[SegmentType, int], key: SegmentType, amount: int) -> None:
    if amount:
        counter[key] = counter.get(key, 0) + amount


def _announce(segment: Segment, lang: str) -> str:
    """Okunmayan bir bloğun yerine geçecek kısa anons cümlesi.

    Cümlenin tamamı çevrilir; parça parça birleştirilseydi dillerin sözcük
    sırası bozulurdu ("Python kod bloğu" → "code block Python" gibi).
    """
    if segment.type is SegmentType.CODE_BLOCK:
        name = _language_name(segment.language)
        kalip = (
            "Burada {count} satırlık bir {language} kod bloğu var."
            if name
            else "Burada {count} satırlık bir kod bloğu var."
        )
        return in_language(kalip, lang).format(
            count=segment.line_count, language=name
        )

    if segment.type is SegmentType.TABLE:
        return in_language(
            "Burada {count} satırlık bir tablo var.", lang
        ).format(count=segment.line_count)

    return in_language("Burada okunmayan bir bölüm var.", lang)


def _language_name(language: str | None) -> str | None:
    """Kod bloğu dil etiketini okunabilir bir isme çevirir."""
    if not language:
        return None
    return _LANGUAGE_NAMES.get(language.lower(), language)


def _render(
    segment: Segment, config: Config, lang: str
) -> tuple[str, dict[SegmentType, int]]:
    """Okunacak bir segmenti seslendirmeye hazır metne çevirir.

    İkinci değer, satır içinde okunmadan geçilen öğelerin sayımıdır; blok
    seviyesindeki atlamalarla aynı rapora girer.
    """
    if segment.type is SegmentType.CODE_BLOCK:
        # Politika "oku" ise kodu ham hâliyle veririz; normalizasyon kodu bozar.
        return segment.text.strip(), {}

    text, skipped = _normalize_inline(segment.text, config, lang)
    if not text:
        return "", skipped

    # Başlık ve liste maddeleri çoğu zaman noktalamasız biter; nokta eklemek
    # TTS'in araya doğal bir duraklama koymasını sağlar.
    if segment.type in (SegmentType.HEADING, SegmentType.LIST_ITEM):
        if text[-1] not in ".!?:;,":
            text += "."

    return text, skipped


def _normalize_inline(
    text: str, config: Config, lang: str
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
        lang,
    )
    _tally(skipped, SegmentType.INLINE_CODE, count)

    text, count = _substitute_inline(
        _BARE_URL_RE,
        text,
        config.policy.get(SegmentType.URL, Action.SKIP),
        SegmentType.URL,
        lambda m: m.group(0).strip("<>"),
        lang,
    )
    _tally(skipped, SegmentType.URL, count)

    # URL'lerden sonra gelmeli: aksi hâlde bağlantı adreslerinin içindeki
    # `/dosya.html` parçaları yol sanılırdı. Bu tipte READ, yolun tamamını
    # değil yalnızca dosya adını okumak demektir; "es-er-se bölü pakize bölü
    # models nokta pe ye" dinlenebilir bir şey değil.
    text, count = _substitute_inline(
        _FILE_PATH_RE,
        text,
        config.policy.get(SegmentType.FILE_PATH, Action.READ),
        SegmentType.FILE_PATH,
        lambda m: m.group("name"),
        lang,
    )
    _tally(skipped, SegmentType.FILE_PATH, count)

    text = _EMPHASIS_RE.sub(lambda m: m.group(2), text)
    text = _UNDERSCORE_EMPHASIS_RE.sub(lambda m: m.group(2), text)
    text = _LEFTOVER_MARKS_RE.sub("", text)

    if config.normalize_decimals:
        text = normalize_decimals(text)

    return _WHITESPACE_RE.sub(" ", text).strip(), skipped


def _substitute_inline(
    pattern: re.Pattern[str],
    text: str,
    action: Action,
    segment_type: SegmentType,
    read_value,
    lang: str,
) -> tuple[str, int]:
    """Satır içi bir örüntüyü politikaya göre okur, anons eder veya siler.

    Dönen sayı, okunmadan geçilen eşleşme adedidir (READ ise sıfır).
    """
    if action is Action.READ:
        return pattern.sub(read_value, text), 0

    replacement = (
        in_language(_INLINE_ANNOUNCEMENTS[segment_type], lang)
        if action is Action.ANNOUNCE
        else ""
    )
    result, count = pattern.subn(replacement, text)
    return result, count
