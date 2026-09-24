"""Sesli uyarı testleri.

Hermetiktir: seslendirme yamalanır, önbellek geçici klasöre yönlendirilir.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from pakize import notices
from pakize.config import Config


@pytest.fixture
def cache(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path / "pakize" / "notices"


@pytest.fixture
def synthesized(monkeypatch) -> list[dict]:
    """`synthesize`'ı yamalar; her çağrının metnini ve config'ini kaydeder."""
    calls: list[dict] = []

    def fake_synthesize(text, destination, config, progress=None, on_part_ready=None):
        calls.append({"text": text, "config": config})
        destination.write_bytes(b"fake-mp3")

    monkeypatch.setattr(notices, "synthesize", fake_synthesize)
    return calls


def test_uyari_ilk_seferde_uretilip_onbellege_yazilir(cache, synthesized):
    path = notices.rate_limit_notice(Config())

    assert path.parent == cache
    assert path.read_bytes() == b"fake-mp3"
    assert len(synthesized) == 1


def test_onbellekteki_uyari_yeniden_uretilmez(cache, synthesized):
    first = notices.rate_limit_notice(Config())
    second = notices.rate_limit_notice(Config())

    assert first == second
    assert len(synthesized) == 1


def test_uyari_cevrilmeden_seslendirilir(cache, synthesized):
    notices.rate_limit_notice(replace(Config(), translate_to="tr"))

    assert synthesized[0]["config"].translate_to is None


def test_ses_degisince_uyari_yeniden_uretilir(cache, synthesized):
    first = notices.rate_limit_notice(replace(Config(), voice="tr-TR-EmelNeural"))
    second = notices.rate_limit_notice(replace(Config(), voice="tr-TR-AhmetNeural"))

    assert first != second
    assert len(synthesized) == 2


def test_uyari_sesin_dilinde_konusur(cache, synthesized):
    notices.rate_limit_notice(replace(Config(), voice="tr-TR-EmelNeural"))
    notices.rate_limit_notice(replace(Config(), voice="en-US-AndrewNeural"))

    assert synthesized[0]["text"].startswith("Çeviri şu an kullanılamıyor.")
    assert synthesized[1]["text"].startswith("Translation is unavailable")


def test_uretim_yarida_kalirsa_dosya_birakilmaz(cache, monkeypatch):
    def failing_synthesize(text, destination, config, progress=None, on_part_ready=None):
        destination.write_bytes(b"half")
        raise RuntimeError("edge-tts düştü")

    monkeypatch.setattr(notices, "synthesize", failing_synthesize)

    with pytest.raises(RuntimeError):
        notices.rate_limit_notice(Config())

    assert list(cache.iterdir()) == []


def test_gecici_dosya_uzantisini_korur(cache, monkeypatch):
    """ffmpeg çıktı biçimini uzantıdan seçer; geçici ad onu bozmamalı."""
    destinations: list[Path] = []

    def fake_synthesize(text, destination, config, progress=None, on_part_ready=None):
        destinations.append(destination)
        destination.write_bytes(b"fake-mp3")

    monkeypatch.setattr(notices, "synthesize", fake_synthesize)

    notices.rate_limit_notice(Config())

    assert destinations[0].suffix == ".mp3"
