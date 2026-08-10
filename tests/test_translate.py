"""Çeviri katmanı testleri.

Hermetiktir: ağa çıkılmaz, `urlopen` yamalanır.
"""

import io
import json
import urllib.error

import pytest

from pakize import translate as translate_modulu
from pakize.models import Segment, SegmentType
from pakize.translate import (
    GoogleTranslator,
    TranslationError,
    translate_segments,
)


def _yanit(metin: str, detected: str = "en") -> io.BytesIO:
    """Ucun döndürdüğü biçimde bir yanıt gövdesi üretir."""
    govde = [[[metin, "kaynak", None, None]], None, detected]
    return io.BytesIO(json.dumps(govde).encode("utf-8"))


@pytest.fixture
def servis(monkeypatch):
    """`urlopen`'ı yamalar; gönderilen metinleri kaydeder, yanıtı ayarlatır."""
    kayit: list[str] = []
    # Gerçek servis gibi satır satır çevirir; satır sayısını korur.
    ayar = {
        "cevirici": lambda metin: "\n".join(f"[{s}]" for s in metin.split("\n")),
        "detected": "en",
        "hatalar": [],
    }

    class SahteYanit:
        def __init__(self, body):
            self._body = body

        def read(self, *args):
            return self._body.read(*args)

        def __enter__(self):
            return self._body

        def __exit__(self, *args):
            return False

    def sahte_urlopen(request, timeout=None):
        if ayar["hatalar"]:
            hata = ayar["hatalar"].pop(0)
            if hata is not None:
                raise hata
        import urllib.parse

        sorgu = urllib.parse.urlparse(request.full_url).query
        metin = urllib.parse.parse_qs(sorgu)["q"][0]
        kayit.append(metin)
        return SahteYanit(_yanit(ayar["cevirici"](metin), ayar["detected"]))

    monkeypatch.setattr(translate_modulu.urllib.request, "urlopen", sahte_urlopen)
    monkeypatch.setattr(translate_modulu.time, "sleep", lambda saniye: None)
    return type("Kurulum", (), {"kayit": kayit, "ayar": ayar})


@pytest.fixture
def translator() -> GoogleTranslator:
    return GoogleTranslator(target="tr", pause_seconds=0)


def test_tek_satir_cevrilir(translator, servis):
    assert translator.translate_lines(["Hello"]) == ["[Hello]"]


def test_satirlar_tek_istekte_toplu_gonderilir(translator, servis):
    """Kitap ölçeğinde istek sayısını düşüren asıl davranış bu."""
    servis.ayar["cevirici"] = lambda metin: metin.upper()

    sonuc = translator.translate_lines(["bir", "iki", "üç"])

    assert sonuc == ["BIR", "IKI", "ÜÇ"]
    assert len(servis.kayit) == 1


def test_satir_sayisi_bozulursa_tek_tek_cevrilir(translator, servis):
    """Servis satır sayısını değiştirirse sıra bozulur; teker teker gidilir."""
    cagri = {"sayi": 0}

    def bozuk(metin):
        cagri["sayi"] += 1
        # İlk (toplu) istekte satır sayısını bozar.
        return metin.replace("\n", " ") if cagri["sayi"] == 1 else f"[{metin}]"

    servis.ayar["cevirici"] = bozuk

    sonuc = translator.translate_lines(["bir", "iki"])

    assert sonuc == ["[bir]", "[iki]"]
    assert len(servis.kayit) == 3  # 1 toplu (bozuk) + 2 tek tek


def test_uzun_metin_birden_cok_istege_bolunur(translator, servis, monkeypatch):
    monkeypatch.setattr(translate_modulu, "MAX_REQUEST_CHARS", 50)

    translator.translate_lines(["A" * 40, "B" * 40, "C" * 40])

    assert len(servis.kayit) == 3


def test_bos_satir_aga_cikmaz(translator, servis):
    assert translator.translate_lines(["   "]) == ["   "]
    assert servis.kayit == []


def test_hiz_sinirinda_tekrar_denenir(translator, servis):
    servis.ayar["hatalar"] = [
        urllib.error.HTTPError("u", 429, "Too Many", {}, None),
        None,
    ]

    assert translator.translate_lines(["Hello"]) == ["[Hello]"]


def test_kalici_hata_tekrar_denenmez(translator, servis):
    servis.ayar["hatalar"] = [urllib.error.HTTPError("u", 400, "Bad", {}, None)]

    with pytest.raises(TranslationError, match="HTTP 400"):
        translator.translate_lines(["Hello"])


def test_surekli_basarisizlik_anlamli_hata_verir(translator, servis):
    servis.ayar["hatalar"] = [urllib.error.URLError("ağ yok")] * 10

    with pytest.raises(TranslationError, match="ulaşılamadı"):
        translator.translate_lines(["Hello"])


def test_yalnizca_metin_segmentleri_cevrilir(translator, servis):
    segments = [
        Segment(SegmentType.HEADING, "Title"),
        Segment(SegmentType.PROSE, "Body text"),
        Segment(SegmentType.CODE_BLOCK, "x = 1", language="py"),
        Segment(SegmentType.TABLE, "| a | b |"),
        Segment(SegmentType.LIST_ITEM, "an item"),
        Segment(SegmentType.QUOTE, "a quote"),
    ]

    sonuc = translate_segments(segments, translator)

    assert sonuc[2].text == "x = 1"  # kod dokunulmadı
    assert sonuc[3].text == "| a | b |"  # tablo dokunulmadı
    assert sonuc[0].text == "[Title]"
    assert sonuc[4].text == "[an item]"
    assert sonuc[5].text == "[a quote]"


def test_kod_blogu_hic_gonderilmez(translator, servis):
    segments = [Segment(SegmentType.CODE_BLOCK, "gizli kod", language="py")]

    translate_segments(segments, translator)

    assert servis.kayit == []


def test_kaynak_dil_hedefle_ayniysa_dokunulmaz(translator, servis):
    servis.ayar["detected"] = "tr"
    segments = [Segment(SegmentType.PROSE, "Zaten Türkçe.")]

    sonuc = translate_segments(segments, translator)

    assert sonuc[0].text == "Zaten Türkçe."


def test_segment_tipi_ve_meta_korunur(translator, servis):
    segments = [Segment(SegmentType.HEADING, "Title", line_count=1, level=2)]

    sonuc = translate_segments(segments, translator)

    assert sonuc[0].type is SegmentType.HEADING
    assert sonuc[0].level == 2


def test_cevrilecek_bir_sey_yoksa_aga_cikilmaz(translator, servis):
    segments = [Segment(SegmentType.HORIZONTAL_RULE, "---")]

    assert translate_segments(segments, translator) == segments
    assert servis.kayit == []


def test_cok_satirli_segment_tek_satira_indirgenir(translator, servis):
    """Satır sayısı korunmazsa segmentlerin sırası karışır."""
    segments = [Segment(SegmentType.QUOTE, "ilk satır\nikinci satır")]

    translate_segments(segments, translator)

    assert "\n" not in servis.kayit[0]
