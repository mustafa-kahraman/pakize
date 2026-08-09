"""Türkçe metin normalizasyonu testleri."""

import pytest

from pakize.parsing.text import normalize_decimals


@pytest.mark.parametrize(
    ("girdi", "beklenen"),
    [
        ("Hızı 1.15 yaptım.", "Hızı 1,15 yaptım."),
        ("0.5 saniye sürdü.", "0,5 saniye sürdü."),
        ("Sonuç 12.75 oldu.", "Sonuç 12,75 oldu."),
    ],
)
def test_ondalik_nokta_virgule_cevrilir(girdi, beklenen):
    assert normalize_decimals(girdi) == beklenen


@pytest.mark.parametrize(
    "girdi",
    [
        "Sürüm 1.2.3 yayınlandı.",
        "IP adresi 192.168.1.1 olsun.",
        "Tarih 09.08.2026 idi.",
        "Etiket 3.10rc1 kullanıldı.",
        "Dosya models.py içinde.",
        "Nokta yok burada 115 var.",
    ],
)
def test_ondalik_olmayan_kaliplar_korunur(girdi):
    assert normalize_decimals(girdi) == girdi


def test_cumle_sonu_noktasi_etkilenmez():
    metin = "Birinci cümle. 2 numaralı madde."

    assert normalize_decimals(metin) == metin


def test_ayni_cumlede_birden_cok_ondalik():
    assert normalize_decimals("1.15 ve 1.25 arası.") == "1,15 ve 1,25 arası."
