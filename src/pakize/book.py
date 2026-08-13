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
        genislik = len(str(total))
        return f"{self.number:0{genislik}d}-{slugify(self.title)}{suffix}"


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
    bolumler = _split_by_headings(text, level)
    if bolumler:
        return bolumler
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
    uretilen: list[Path] = []
    atlanan = 0

    for chapter in chapters:
        hedef = destination / chapter.filename(len(chapters))
        zaten_var = not force and hedef.is_file() and hedef.stat().st_size > 0

        if progress is not None:
            progress(chapter, len(chapters), zaten_var)

        if not zaten_var:
            _narrate_chapter(chapter, hedef, config)

        uretilen.append(hedef)
        atlanan += int(zaten_var)

    playlist = _write_playlist(destination, chapters, uretilen)
    return BookResult(
        directory=destination,
        chapters=uretilen,
        playlist=playlist,
        skipped=atlanan,
    )


def slugify(title: str) -> str:
    """Başlığı dosya adına uygun, ASCII bir kısa ada çevirir."""
    ascii_hali = unicodedata.normalize("NFKD", title.translate(_TURKISH_MAP))
    ascii_hali = ascii_hali.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_hali).strip("-")
    return (slug[:60].rstrip("-")) or "bolum"


def _narrate_chapter(chapter: Chapter, destination: Path, config: Config) -> SpeechResult:
    """Tek bir bölümü seslendirir; başlık da metnin başında okunur."""
    metin = f"{chapter.title}\n\n{chapter.text}" if chapter.title else chapter.text
    return synthesize(metin, destination, config)


def _split_by_headings(text: str, level: int) -> list[Chapter]:
    """Başlıklara göre böler; hiç uygun başlık yoksa boş liste döner."""
    satirlar = text.replace("\r\n", "\n").split("\n")
    sinirlar: list[tuple[int, str]] = []

    icerideyiz_kod = False
    for index, satir in enumerate(satirlar):
        # Kod bloğu içindeki `#` satırları başlık değildir.
        if satir.lstrip().startswith(("```", "~~~")):
            icerideyiz_kod = not icerideyiz_kod
            continue
        if icerideyiz_kod:
            continue
        match = _HEADING_RE.match(satir)
        if match and len(match.group("hashes")) <= level:
            sinirlar.append((index, match.group("title")))

    if not sinirlar:
        return []

    bolumler: list[Chapter] = []
    for sira, (baslangic, baslik) in enumerate(sinirlar):
        bitis = sinirlar[sira + 1][0] if sira + 1 < len(sinirlar) else len(satirlar)
        govde = "\n".join(satirlar[baslangic + 1 : bitis]).strip()
        if not govde:
            continue
        bolumler.append(
            Chapter(number=len(bolumler) + 1, title=baslik.strip(), text=govde)
        )

    # İlk başlıktan önceki metin (ön söz, kapak) kaybolmasın.
    onsoz = "\n".join(satirlar[: sinirlar[0][0]]).strip()
    if onsoz:
        bolumler = [Chapter(number=1, title="", text=onsoz)] + [
            Chapter(number=b.number + 1, title=b.title, text=b.text) for b in bolumler
        ]

    return bolumler


def _split_by_size(text: str) -> list[Chapter]:
    """Başlıksız metni, paragraf sınırlarına saygı duyarak parçalara böler."""
    paragraflar = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraflar:
        return []

    bolumler: list[Chapter] = []
    tampon: list[str] = []
    uzunluk = 0

    for paragraf in paragraflar:
        tampon.append(paragraf)
        uzunluk += len(paragraf)
        if uzunluk >= FALLBACK_CHAPTER_CHARS:
            bolumler.append(_bolum_yap(len(bolumler) + 1, tampon))
            tampon, uzunluk = [], 0

    if tampon:
        bolumler.append(_bolum_yap(len(bolumler) + 1, tampon))
    return bolumler


def _bolum_yap(number: int, paragraflar: list[str]) -> Chapter:
    return Chapter(number=number, title=f"Bölüm {number}", text="\n\n".join(paragraflar))


def _write_playlist(
    directory: Path, chapters: list[Chapter], files: list[Path]
) -> Path:
    """Bölümleri sırayla çalan bir M3U oynatma listesi yazar."""
    playlist = directory / f"{directory.name}.m3u"
    satirlar = ["#EXTM3U"]
    for chapter, path in zip(chapters, files):
        satirlar.append(f"#EXTINF:-1,{chapter.title or f'Bölüm {chapter.number}'}")
        satirlar.append(path.name)
    playlist.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return playlist
