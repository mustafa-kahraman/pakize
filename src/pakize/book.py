"""Uzun metinleri bölüm bölüm seslendirme.

Bir kitap 8-10 saatlik ses demek. Tek dosya üretmek iki soruna yol açar:
kaldığın yeri bulamazsın ve üretim yarıda kesilirse baştan başlaman gerekir.
Bu yüzden her bölüm ayrı dosyaya yazılır, var olan dosyalar atlanır ve yanına
bir oynatma listesi bırakılır.

Metin dışı biçimler (EPUB, PDF, MOBI) Calibre'nin `ebook-convert` aracıyla
Markdown'a çevrilir; başlıklar korunduğu için bölüm ayrımı buradan çıkar.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .i18n import _
from .pipeline import SpeechResult, synthesize
from .platforms import install_hint

TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".text"})
"""Doğrudan okunabilen biçimler; diğerleri önce dönüştürülür."""

CONVERTER = "ebook-convert"
DEFAULT_HEADING_LEVEL = 2
"""Bu seviyeye kadar olan başlıklar bölüm başlangıcı sayılır."""

FALLBACK_CHAPTER_CHARS = 12_000
"""Başlık bulunmayan metinlerde bir bölümün hedeflenen uzunluğu."""

_HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_TURKISH_MAP = str.maketrans(
    {
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i",
        "İ": "i", "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
    }
)


class BookError(RuntimeError):
    """Kitap okunamadığında veya dönüştürülemediğinde oluşan hata."""


@dataclass(frozen=True)
class Chapter:
    """Kitabın tek bir bölümü."""

    number: int
    title: str
    text: str

    def filename(self, total: int, suffix: str = ".mp3") -> str:
        """Sıralı ve okunabilir dosya adı üretir.

        Numara toplam bölüm sayısına göre sıfırla doldurulur; böylece dosyalar
        alfabetik sıralamada da doğru sırada durur.
        """
        width = len(str(total))
        return f"{self.number:0{width}d}-{slugify(self.title)}{suffix}"


@dataclass(frozen=True)
class BookResult:
    """Tamamlanmış bir kitap seslendirmesinin sonucu."""

    directory: Path
    chapters: list[Path]
    playlist: Path
    skipped: int
    """Zaten var olduğu için yeniden üretilmeyen bölüm sayısı."""


ProgressCallback = Callable[[Chapter, int, bool], None]
"""(bölüm, toplam, atlandı_mı) ile her bölüm için çağrılır."""


def load_text(path: Path) -> str:
    """Kitabı düz metne çevirir.

    Metin biçimleri doğrudan okunur; EPUB/PDF/MOBI gibi biçimler için
    `ebook-convert` çağrılır. Markdown çıktısı istenir, çünkü başlıklar bölüm
    ayrımının tek güvenilir kaynağıdır.
    """
    if not path.is_file():
        raise BookError(_("Dosya bulunamadı: {path}").format(path=path))

    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")

    converter = shutil.which(CONVERTER)
    if converter is None:
        raise BookError(
            _(
                "{suffix} biçimi için {converter} gerekli "
                "(Calibre ile gelir): {hint}"
            ).format(
                suffix=path.suffix, converter=CONVERTER, hint=install_hint("calibre")
            )
        )

    with tempfile.TemporaryDirectory(prefix="pakize-kitap-") as workdir:
        target = Path(workdir) / "kitap.txt"
        result = subprocess.run(
            [
                converter,
                str(path),
                str(target),
                "--txt-output-formatting=markdown",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not target.is_file():
            raise BookError(
                _("{converter} dönüştürme başarısız: {error}").format(
                    converter=CONVERTER, error=result.stderr.strip()[:400]
                )
            )
        return target.read_text(encoding="utf-8", errors="replace")


def split_chapters(
    text: str, level: int = DEFAULT_HEADING_LEVEL
) -> list[Chapter]:
    """Metni bölümlere ayırır.

    Başlıklar bulunursa bölüm sınırı onlardır. Hiç başlık yoksa metin, boş
    satırlara saygı duyularak yaklaşık eşit parçalara bölünür — aksi hâlde
    tüm kitap tek bir devasa dosyaya düşerdi.
    """
    chapters = _split_by_headings(text, level)
    if chapters:
        return chapters
    return _split_by_size(text)


def narrate(
    source: Path,
    destination: Path,
    config: Config,
    level: int = DEFAULT_HEADING_LEVEL,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> BookResult:
    """Kitabı bölüm bölüm seslendirip `destination` dizinine yazar.

    Var olan bölüm dosyaları yeniden üretilmez; yarıda kalan bir iş aynı
    komutla kaldığı yerden devam eder. `force` bunu devre dışı bırakır.
    """
    chapters = split_chapters(load_text(source), level)
    if not chapters:
        raise BookError(_("Kitapta seslendirilecek metin bulunamadı"))

    destination.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []
    skipped = 0

    for chapter in chapters:
        target = destination / chapter.filename(len(chapters))
        already_exists = not force and target.is_file() and target.stat().st_size > 0

        if progress is not None:
            progress(chapter, len(chapters), already_exists)

        if not already_exists:
            _narrate_chapter(chapter, target, config)

        produced.append(target)
        skipped += int(already_exists)

    playlist = _write_playlist(destination, chapters, produced)
    return BookResult(
        directory=destination,
        chapters=produced,
        playlist=playlist,
        skipped=skipped,
    )


def slugify(title: str) -> str:
    """Başlığı dosya adına uygun, ASCII bir kısa ada çevirir."""
    ascii_form = unicodedata.normalize("NFKD", title.translate(_TURKISH_MAP))
    ascii_form = ascii_form.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_form).strip("-")
    return (slug[:60].rstrip("-")) or "bolum"


def _narrate_chapter(chapter: Chapter, destination: Path, config: Config) -> SpeechResult:
    """Tek bir bölümü seslendirir; başlık da metnin başında okunur."""
    text = f"{chapter.title}\n\n{chapter.text}" if chapter.title else chapter.text
    return synthesize(text, destination, config)


def _split_by_headings(text: str, level: int) -> list[Chapter]:
    """Başlıklara göre böler; hiç uygun başlık yoksa boş liste döner."""
    lines = text.replace("\r\n", "\n").split("\n")
    bounds: list[tuple[int, str]] = []

    in_code_block = False
    for index, line in enumerate(lines):
        # Kod bloğu içindeki `#` satırları başlık değildir.
        if line.lstrip().startswith(("```", "~~~")):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        match = _HEADING_RE.match(line)
        if match and len(match.group("hashes")) <= level:
            bounds.append((index, match.group("title")))

    if not bounds:
        return []

    chapters: list[Chapter] = []
    for number, (start, heading) in enumerate(bounds):
        end = bounds[number + 1][0] if number + 1 < len(bounds) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        if not body:
            continue
        chapters.append(
            Chapter(number=len(chapters) + 1, title=heading.strip(), text=body)
        )

    # İlk başlıktan önceki metin (ön söz, kapak) kaybolmasın.
    preface = "\n".join(lines[: bounds[0][0]]).strip()
    if preface:
        chapters = [Chapter(number=1, title="", text=preface)] + [
            Chapter(number=b.number + 1, title=b.title, text=b.text) for b in chapters
        ]

    return chapters


def _split_by_size(text: str) -> list[Chapter]:
    """Başlıksız metni, paragraf sınırlarına saygı duyarak parçalara böler."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chapters: list[Chapter] = []
    buffer: list[str] = []
    length = 0

    for paragraph in paragraphs:
        buffer.append(paragraph)
        length += len(paragraph)
        if length >= FALLBACK_CHAPTER_CHARS:
            chapters.append(_split_evenly(len(chapters) + 1, buffer))
            buffer, length = [], 0

    if buffer:
        chapters.append(_split_evenly(len(chapters) + 1, buffer))
    return chapters


def _split_evenly(number: int, paragraphs: list[str]) -> Chapter:
    return Chapter(number=number, title=f"Bölüm {number}", text="\n\n".join(paragraphs))


def _write_playlist(
    directory: Path, chapters: list[Chapter], files: list[Path]
) -> Path:
    """Bölümleri sırayla çalan bir M3U oynatma listesi yazar."""
    playlist = directory / f"{directory.name}.m3u"
    lines = ["#EXTM3U"]
    for chapter, path in zip(chapters, files):
        lines.append(f"#EXTINF:-1,{chapter.title or f'Bölüm {chapter.number}'}")
        lines.append(path.name)
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist
