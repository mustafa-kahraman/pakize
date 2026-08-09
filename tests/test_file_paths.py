"""Dosya yolu tespiti ve politikası testleri."""

from dataclasses import replace

import pytest

from pakize.config import Config
from pakize.models import Action, SegmentType
from pakize.parsing.markdown import parse_segments
from pakize.parsing.policy import apply_policy


@pytest.fixture
def config() -> Config:
    return Config()


def _speak(text: str, config: Config) -> str:
    utterances, _ = apply_policy(parse_segments(text), config)
    return " ".join(utterances)


@pytest.mark.parametrize(
    ("girdi", "beklenen"),
    [
        ("src/pakize/models.py dosyasına bak.", "models.py dosyasına bak."),
        ("~/.config/pakize/config.toml içinde.", "config.toml içinde."),
        ("/home/mustafa/notlar.md okundu.", "notlar.md okundu."),
        ("tests/test_policy.py çalıştı.", "test_policy.py çalıştı."),
    ],
)
def test_yol_okunurken_yalnizca_dosya_adi_kalir(girdi, beklenen, config):
    assert _speak(girdi, config) == beklenen


@pytest.mark.parametrize(
    "girdi",
    [
        "Bunu ve/veya şunu seç.",
        "Dil TR/EN olabilir.",
        "Oran 3/4 kadar.",
    ],
)
def test_yol_olmayan_egik_cizgiler_bozulmaz(girdi, config):
    assert _speak(girdi, config) == girdi


def test_url_icindeki_yol_parcasi_kapilmaz(config):
    config = replace(config, policy={**config.policy, SegmentType.URL: Action.READ})

    assert _speak("Adres https://ornek.com/klasor/sayfa.html burada.", config) == (
        "Adres https://ornek.com/klasor/sayfa.html burada."
    )


def test_yol_anons_edilebilir(config):
    config = replace(
        config, policy={**config.policy, SegmentType.FILE_PATH: Action.ANNOUNCE}
    )

    utterances, skipped = apply_policy(
        parse_segments("Şu src/pakize/cli.py dosyasına bak."), config
    )

    assert utterances == ["Şu bir dosya yolu dosyasına bak."]
    assert skipped == {SegmentType.FILE_PATH: 1}


def test_yol_atlanabilir(config):
    config = replace(
        config, policy={**config.policy, SegmentType.FILE_PATH: Action.SKIP}
    )

    assert _speak("Şu src/pakize/cli.py dosyası.", config) == "Şu dosyası."


def test_satir_ici_koddaki_yol_da_kisalir(config):
    assert _speak("`src/pakize/audio.py` içinde.", config) == "audio.py içinde."


def test_kod_blogundaki_yol_dokunulmaz(config):
    config = replace(
        config, policy={**config.policy, SegmentType.CODE_BLOCK: Action.READ}
    )

    assert _speak("```\ncat src/pakize/cli.py\n```", config) == "cat src/pakize/cli.py"


def test_ondalik_duzeltme_kapatilabilir(config):
    acik = _speak("Hızı 1.15 yaptım.", config)
    kapali = _speak("Hızı 1.15 yaptım.", replace(config, normalize_decimals=False))

    assert acik == "Hızı 1,15 yaptım."
    assert kapali == "Hızı 1.15 yaptım."
