"""Pakize'nin çekirdek veri tipleri.

Boru hattının tamamı bu tipler üzerinden konuşur: metin önce `Segment`'lere
ayrılır, politika uygulandıktan sonra `Chunk`'lara bölünür, motor da yalnızca
`Chunk` görür. Böylece parser, politika ve TTS motoru birbirinden habersiz kalır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SegmentType(str, Enum):
    """Metin içinde ayırt ettiğimiz blok/öbek türleri.

    Değerler config dosyasında anahtar olarak kullanıldığı için `str` tabanlı.
    """

    PROSE = "prose"
    """Normal düz metin — okunacak asıl içerik."""

    HEADING = "heading"
    """Markdown başlığı (`#`, `##`, ...)."""

    CODE_BLOCK = "code_block"
    """Çitli (``` ) veya girintili kod bloğu."""

    INLINE_CODE = "inline_code"
    """Satır içi `kod` parçası."""

    URL = "url"
    """Çıplak URL veya Markdown bağlantı hedefi."""

    FILE_PATH = "file_path"
    """Metin içinde geçen dosya yolu (`src/pakize/models.py` gibi)."""

    TABLE = "table"
    """Markdown tablosu."""

    LIST_ITEM = "list_item"
    """Sırasız/sıralı liste maddesi."""

    QUOTE = "quote"
    """Alıntı bloğu (`>`)."""

    HORIZONTAL_RULE = "horizontal_rule"
    """Yatay çizgi (`---`, `***`)."""


class Action(str, Enum):
    """Bir segment tipine uygulanacak politika."""

    READ = "read"
    """Segment içeriği olduğu gibi okunur."""

    ANNOUNCE = "announce"
    """İçerik okunmaz; yerine kısa bir Türkçe anons cümlesi seslendirilir."""

    SKIP = "skip"
    """Segment tamamen atlanır, hiçbir ses üretilmez."""


@dataclass(frozen=True)
class Segment:
    """Kaynak metinden ayrıştırılmış tek bir anlamsal blok."""

    type: SegmentType
    text: str
    """Segmentin ham metni (kod bloklarında çit satırları hariç gövde)."""

    line_count: int = 1
    """Kaynaktaki satır sayısı — anons metninde kullanılır."""

    language: str | None = None
    """Kod bloğunun dil etiketi (```python → "python"); yoksa None."""

    level: int | None = None
    """Başlık seviyesi (# → 1); yalnızca HEADING için anlamlı."""


@dataclass(frozen=True)
class Chunk:
    """TTS motoruna tek seferde gönderilecek, sese çevrilebilir metin parçası."""

    text: str
    index: int
    """Sıra numarası — üretilen geçici ses dosyalarını sıralamak için."""

    voice: str | None = None
    """Bu parçaya özel ses; None ise config'teki varsayılan ses kullanılır."""


@dataclass
class SpeechRequest:
    """Boru hattına verilen tek bir seslendirme işi."""

    source_text: str
    chunks: list[Chunk] = field(default_factory=list)
    skipped: dict[SegmentType, int] = field(default_factory=dict)
    """Hangi segment tipinden kaç adet atlandığı — kullanıcıya rapor edilir."""
