"""Segment politikası ve satır içi normalizasyon testleri."""

from dataclasses import replace

import pytest

from pakize.config import Config
from pakize.models import Action, SegmentType
from pakize.parsing.markdown import parse_segments
from pakize.parsing.policy import apply_policy


@pytest.fixture
def config() -> Config:
    return Config()


def _speak(text: str, config: Config) -> list[str]:
    utterances, _ = apply_policy(parse_segments(text), config)
    return utterances


def test_kod_blogu_varsayilan_olarak_anons_edilir(config):
    utterances = _speak("```python\nx = 1\ny = 2\nz = 3\n```", config)

    assert utterances == ["Burada 3 satırlık bir Python kod bloğu var."]


def test_bilinmeyen_dil_etiketi_oldugu_gibi_soylenir(config):
    utterances = _speak("```zig\nconst a = 1;\n```", config)

    assert utterances == ["Burada 1 satırlık bir zig kod bloğu var."]


def test_dilsiz_kod_blogu_anonsu(config):
    assert _speak("```\nls\n```", config) == ["Burada 1 satırlık bir kod bloğu var."]


def test_kod_blogu_atlanabilir(config):
    config = replace(config, policy={**config.policy, SegmentType.CODE_BLOCK: Action.SKIP})

    utterances, skipped = apply_policy(parse_segments("```py\nx=1\n```"), config)

    assert utterances == []
    assert skipped == {SegmentType.CODE_BLOCK: 1}


def test_kod_blogu_okunabilir(config):
    config = replace(config, policy={**config.policy, SegmentType.CODE_BLOCK: Action.READ})

    assert _speak("```py\nx = 1\n```", config) == ["x = 1"]


def test_tablo_anonsu_ayrac_satirini_saymaz(config):
    text = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"

    assert _speak(text, config) == ["Burada 2 satırlık bir tablo var."]


def test_satir_ici_kod_varsayilan_olarak_okunur(config):
    assert _speak("`build_chunks` fonksiyonu böler.", config) == [
        "build_chunks fonksiyonu böler."
    ]


def test_satir_ici_kod_anons_edilebilir(config):
    config = replace(
        config, policy={**config.policy, SegmentType.INLINE_CODE: Action.ANNOUNCE}
    )

    assert _speak("Burada `x = 1` var.", config) == ["Burada bir kod parçası var."]


def test_ciplak_url_varsayilan_olarak_atilir(config):
    assert _speak("Kaynak https://edge-tts.com/ adresinde.", config) == [
        "Kaynak adresinde."
    ]


def test_markdown_baglantisinda_metin_kalir_url_gider(config):
    assert _speak("[Şu sayfaya](https://ornek.com/a) bak.", config) == [
        "Şu sayfaya bak."
    ]


def test_gorsel_alt_metni_okunur(config):
    assert _speak("![mimari şeması](a.png) inceledim.", config) == [
        "mimari şeması inceledim."
    ]


def test_vurgu_isaretleri_temizlenir(config):
    assert _speak("Bu **çok** önemli ve _acil_ bir ~~konu~~.", config) == [
        "Bu çok önemli ve acil bir konu."
    ]


def test_baslik_ve_liste_sonuna_nokta_eklenir(config):
    assert _speak("# Kurulum", config) == ["Kurulum."]
    assert _speak("- ilk madde", config) == ["ilk madde."]


def test_zaten_noktalamali_baslik_ikinci_nokta_almaz(config):
    assert _speak("## Hazır mı?", config) == ["Hazır mı?"]


def test_yatay_cizgi_atlanir(config):
    utterances, skipped = apply_policy(parse_segments("Metin.\n\n---\n\nDevam."), config)

    assert utterances == ["Metin.", "Devam."]
    assert skipped == {SegmentType.HORIZONTAL_RULE: 1}


def test_atlanan_segmentler_sayilir(config):
    text = "```py\nx=1\n```\n\n```js\ny=2\n```\n\nhttps://a.com\n"

    _, skipped = apply_policy(parse_segments(text), config)

    assert skipped == {SegmentType.CODE_BLOCK: 2, SegmentType.URL: 1}


def test_sadece_urlden_olusan_paragraf_bos_soyleyis_uretmez(config):
    assert _speak("https://ornek.com", config) == []
