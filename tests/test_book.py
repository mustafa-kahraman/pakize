"""Kitap seslendirme testleri.

Hermetiktir: TTS çağrılmaz, `ebook-convert` çalıştırılmaz; ikisi de yamalanır.
"""

from pathlib import Path

import pytest

from pakize import book
from pakize.book import BookError, Chapter
from pakize.config import Config

KITAP = """Kapak metni burada.

# Birinci Bölüm

Birinci bölümün gövdesi.

## Alt Başlık

Alt başlığın gövdesi.

# İkinci Bölüm

İkinci bölümün gövdesi.
"""


@pytest.fixture
def seslendirilen(monkeypatch) -> list[tuple[str, Path]]:
    """`synthesize`'ı yamalar; sese çevrilen metni ve hedefi kaydeder."""
    kayit: list[tuple[str, Path]] = []

    def sahte(text, destination, config, progress=None, on_part_ready=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte ses")
        kayit.append((text, destination))
        return None

    monkeypatch.setattr(book, "synthesize", sahte)
    return kayit


@pytest.fixture
def kitap_dosyasi(tmp_path) -> Path:
    path = tmp_path / "kitap.md"
    path.write_text(KITAP, encoding="utf-8")
    return path


def test_basliklara_gore_bolunur():
    bolumler = book.split_chapters(KITAP, level=1)

    assert [b.title for b in bolumler] == ["", "Birinci Bölüm", "İkinci Bölüm"]


def test_seviye_alt_baslıkları_da_kapsayabilir():
    bolumler = book.split_chapters(KITAP, level=2)

    assert [b.title for b in bolumler] == [
        "",
        "Birinci Bölüm",
        "Alt Başlık",
        "İkinci Bölüm",
    ]


def test_ilk_basliktan_onceki_metin_kaybolmaz():
    bolumler = book.split_chapters(KITAP, level=1)

    assert bolumler[0].text == "Kapak metni burada."
    assert bolumler[0].number == 1


def test_bolum_numaralari_ardisiktir():
    bolumler = book.split_chapters(KITAP, level=2)

    assert [b.number for b in bolumler] == [1, 2, 3, 4]


def test_bos_govdeli_baslik_bolum_uretmez():
    bolumler = book.split_chapters("# Boş Başlık\n\n# Dolu\n\ngövde\n", level=1)

    assert [b.title for b in bolumler] == ["Dolu"]


def test_kod_blogundaki_diyez_baslik_sayilmaz():
    metin = "# Gerçek Başlık\n\ngövde\n\n```bash\n# bu bir yorum\n```\n"

    bolumler = book.split_chapters(metin, level=1)

    assert len(bolumler) == 1


def test_basliksiz_metin_boyuta_gore_bolunur(monkeypatch):
    monkeypatch.setattr(book, "FALLBACK_CHAPTER_CHARS", 100)
    metin = "\n\n".join("A" * 60 for _ in range(10))

    bolumler = book.split_chapters(metin)

    assert len(bolumler) > 1
    assert all(b.title.startswith("Bölüm") for b in bolumler)


def test_basliksiz_bolme_paragrafi_ortadan_kesmez(monkeypatch):
    monkeypatch.setattr(book, "FALLBACK_CHAPTER_CHARS", 50)
    metin = "birinci paragraf\n\nikinci paragraf\n\nüçüncü paragraf"

    birlesik = " ".join(b.text for b in book.split_chapters(metin))

    for parca in ("birinci paragraf", "ikinci paragraf", "üçüncü paragraf"):
        assert parca in birlesik


def test_bos_metin_bolum_uretmez():
    assert book.split_chapters("   \n\n  ") == []


@pytest.mark.parametrize(
    ("baslik", "beklenen"),
    [
        ("İkinci Bölüm", "ikinci-bolum"),
        ("Şuğüç Öİ", "suguc-oi"),
        ("Task 2: Conversion", "task-2-conversion"),
        ("!!!", "bolum"),
        ("", "bolum"),
    ],
)
def test_slug_turkce_karakterleri_cevirir(baslik, beklenen):
    assert book.slugify(baslik) == beklenen


def test_dosya_adi_toplama_gore_sifirla_doldurulur():
    chapter = Chapter(number=7, title="Giriş", text="x")

    assert chapter.filename(total=9) == "7-giris.mp3"
    assert chapter.filename(total=120) == "007-giris.mp3"


def test_her_bolum_ayri_dosyaya_yazilir(kitap_dosyasi, tmp_path, seslendirilen):
    sonuc = book.narrate(kitap_dosyasi, tmp_path / "cikti", Config(), level=1)

    assert len(sonuc.chapters) == 3
    assert all(path.is_file() for path in sonuc.chapters)


def test_baslik_metnin_basinda_okunur(kitap_dosyasi, tmp_path, seslendirilen):
    book.narrate(kitap_dosyasi, tmp_path / "cikti", Config(), level=1)

    metinler = [metin for metin, _ in seslendirilen]
    assert metinler[1].startswith("Birinci Bölüm")


def test_var_olan_bolumler_yeniden_uretilmez(kitap_dosyasi, tmp_path, seslendirilen):
    hedef = tmp_path / "cikti"
    book.narrate(kitap_dosyasi, hedef, Config(), level=1)
    seslendirilen.clear()

    sonuc = book.narrate(kitap_dosyasi, hedef, Config(), level=1)

    assert seslendirilen == []
    assert sonuc.skipped == 3


def test_eksik_bolum_tamamlanir(kitap_dosyasi, tmp_path, seslendirilen):
    """Yarıda kalan iş, aynı komutla kaldığı yerden devam etmeli."""
    hedef = tmp_path / "cikti"
    sonuc = book.narrate(kitap_dosyasi, hedef, Config(), level=1)
    sonuc.chapters[1].unlink()
    seslendirilen.clear()

    yeni = book.narrate(kitap_dosyasi, hedef, Config(), level=1)

    assert len(seslendirilen) == 1
    assert yeni.skipped == 2


def test_bos_dosya_yeniden_uretilir(kitap_dosyasi, tmp_path, seslendirilen):
    """Yarım kalmış sıfır baytlık dosya, üretilmiş sayılmamalı."""
    hedef = tmp_path / "cikti"
    sonuc = book.narrate(kitap_dosyasi, hedef, Config(), level=1)
    sonuc.chapters[0].write_bytes(b"")
    seslendirilen.clear()

    book.narrate(kitap_dosyasi, hedef, Config(), level=1)

    assert len(seslendirilen) == 1


def test_force_hepsini_yeniden_uretir(kitap_dosyasi, tmp_path, seslendirilen):
    hedef = tmp_path / "cikti"
    book.narrate(kitap_dosyasi, hedef, Config(), level=1)
    seslendirilen.clear()

    sonuc = book.narrate(kitap_dosyasi, hedef, Config(), level=1, force=True)

    assert len(seslendirilen) == 3
    assert sonuc.skipped == 0


def test_oynatma_listesi_sirali_yazilir(kitap_dosyasi, tmp_path, seslendirilen):
    sonuc = book.narrate(kitap_dosyasi, tmp_path / "cikti", Config(), level=1)

    icerik = sonuc.playlist.read_text(encoding="utf-8")

    assert icerik.startswith("#EXTM3U")
    assert icerik.index("1-") < icerik.index("2-birinci-bolum")
    assert "Birinci Bölüm" in icerik


def test_ilerleme_her_bolum_icin_bildirilir(kitap_dosyasi, tmp_path, seslendirilen):
    adimlar: list[tuple[int, int, bool]] = []

    book.narrate(
        kitap_dosyasi,
        tmp_path / "cikti",
        Config(),
        level=1,
        progress=lambda c, t, s: adimlar.append((c.number, t, s)),
    )

    assert adimlar == [(1, 3, False), (2, 3, False), (3, 3, False)]


def test_metin_dosyasi_dogrudan_okunur(kitap_dosyasi):
    assert book.load_text(kitap_dosyasi).startswith("Kapak metni")


def test_olmayan_dosya_hata_verir(tmp_path):
    with pytest.raises(BookError, match="bulunamadı"):
        book.load_text(tmp_path / "yok.md")


def test_donusturucu_yoksa_kurulum_ipucu(tmp_path, monkeypatch):
    epub = tmp_path / "kitap.epub"
    epub.write_bytes(b"sahte epub")
    monkeypatch.setattr(book.shutil, "which", lambda name: None)

    with pytest.raises(BookError, match="calibre"):
        book.load_text(epub)


def test_epub_donusturucuden_gecirilir(tmp_path, monkeypatch):
    epub = tmp_path / "kitap.epub"
    epub.write_bytes(b"sahte epub")
    monkeypatch.setattr(book.shutil, "which", lambda name: "/usr/bin/ebook-convert")
    kayit: dict = {}

    class Sonuc:
        returncode = 0
        stderr = ""

    def sahte_run(command, **kwargs):
        kayit["command"] = command
        Path(command[2]).write_text("# Başlık\n\ngövde\n", encoding="utf-8")
        return Sonuc()

    monkeypatch.setattr(book.subprocess, "run", sahte_run)

    metin = book.load_text(epub)

    assert "--txt-output-formatting=markdown" in kayit["command"]
    assert metin.startswith("# Başlık")


def test_donusturme_hatasi_sarilir(tmp_path, monkeypatch):
    epub = tmp_path / "kitap.epub"
    epub.write_bytes(b"sahte epub")
    monkeypatch.setattr(book.shutil, "which", lambda name: "/usr/bin/ebook-convert")

    class Sonuc:
        returncode = 1
        stderr = "bozuk dosya"

    monkeypatch.setattr(book.subprocess, "run", lambda command, **kw: Sonuc())

    with pytest.raises(BookError, match="bozuk dosya"):
        book.load_text(epub)


def test_bos_kitap_anlamli_hata(tmp_path, seslendirilen):
    bos = tmp_path / "bos.md"
    bos.write_text("   \n", encoding="utf-8")

    with pytest.raises(BookError, match="seslendirilecek metin bulunamadı"):
        book.narrate(bos, tmp_path / "cikti", Config())
