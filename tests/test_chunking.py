"""Parçalama (chunking) testleri."""

import pytest

from pakize.chunking import build_chunks


def _texts(utterances: list[str], limit: int) -> list[str]:
    return [chunk.text for chunk in build_chunks(utterances, limit)]


def test_sinira_sigan_soyleyisler_tek_parcada_birlesir():
    chunks = build_chunks(["Bir cümle.", "İkinci cümle."], max_chars=100)

    assert len(chunks) == 1
    assert chunks[0].text == "Bir cümle.\nİkinci cümle."


def test_parca_indeksleri_sirali_verilir():
    chunks = build_chunks(["a" * 40, "b" * 40, "c" * 40], max_chars=50)

    assert [chunk.index for chunk in chunks] == [0, 1, 2]


def test_hicbir_parca_siniri_asmaz():
    utterances = [f"Bu {i}. cümledir ve biraz uzundur." for i in range(30)]

    chunks = build_chunks(utterances, max_chars=80)

    assert all(len(chunk.text) <= 80 for chunk in chunks)


def test_uzun_metin_cumle_sinirinda_bolunur():
    text = "Birinci cümle burada. İkinci cümle burada. Üçüncü cümle burada."

    parts = _texts([text], limit=45)

    assert parts == [
        "Birinci cümle burada. İkinci cümle burada.",
        "Üçüncü cümle burada.",
    ]


def test_ondalikli_sayi_cumle_sonu_sayilmaz():
    text = "Hızı 1.15 yaptım ve bu gayet iyi oldu. Devam edelim."

    parts = _texts([text], limit=200)

    assert parts == [text]


def test_cumle_sigmazsa_virgulden_bolunur():
    text = "Birinci öbek burada, ikinci öbek burada, üçüncü öbek burada."

    parts = _texts([text], limit=30)

    assert all(len(part) <= 30 for part in parts)
    assert len(parts) == 3


def test_tek_kelime_sinirdan_uzunsa_ham_kesilir():
    parts = _texts(["a" * 25], limit=10)

    assert parts == ["a" * 10, "a" * 10, "a" * 5]


def test_icerik_kaybolmaz():
    utterances = ["Birinci cümle burada. İkinci cümle burada.", "Üçüncü söyleyiş."]

    birlesik = " ".join(_texts(utterances, limit=30)).replace("\n", " ")

    for kelime in ("Birinci", "İkinci", "Üçüncü", "söyleyiş."):
        assert kelime in birlesik


def test_bos_soyleyisler_elenir():
    assert build_chunks(["", "   ", "\n"], max_chars=50) == []


def test_gecersiz_sinir_hata_verir():
    with pytest.raises(ValueError):
        build_chunks(["metin"], max_chars=0)
