"""Piper motoru testleri.

Hermetiktir: piper çalıştırılmaz, alt süreç çağrısı yamalanır.
"""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from pakize.config import Config
from pakize.engines import EngineError, EngineUnavailable
from pakize.engines import piper as piper_modulu
from pakize.engines.piper import PiperEngine


@pytest.fixture
def model(tmp_path) -> Path:
    path = tmp_path / "tr_TR-dfki-medium.onnx"
    path.write_bytes(b"sahte model")
    return path


@pytest.fixture
def ikili(tmp_path) -> Path:
    path = tmp_path / "piper"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    return path


@pytest.fixture
def config(model, ikili) -> Config:
    return replace(Config(), engine="piper", piper_model=model, piper_binary=ikili)


@pytest.fixture
def calistirilan(monkeypatch):
    """`create_subprocess_exec`'i yamalar; komutu ve stdin'i kaydeder."""
    kayit: dict = {}
    ayar = {"returncode": 0, "stderr": b"", "ciktiyi_yaz": True}

    class SahteSurec:
        returncode = 0

        async def communicate(self, girdi=None):
            kayit["stdin"] = girdi
            self.returncode = ayar["returncode"]
            if ayar["ciktiyi_yaz"]:
                Path(kayit["cikti"]).write_bytes(b"RIFF sahte wav")
            return (b"", ayar["stderr"])

    async def sahte_exec(*command, **kwargs):
        kayit["command"] = list(command)
        kayit["cikti"] = command[command.index("--output-file") + 1]
        return SahteSurec()

    monkeypatch.setattr(piper_modulu.asyncio, "create_subprocess_exec", sahte_exec)
    return type("Kurulum", (), {"kayit": kayit, "ayar": ayar})


def test_model_yoksa_kullanilamaz(ikili):
    engine = PiperEngine(replace(Config(), piper_binary=ikili))

    with pytest.raises(EngineUnavailable, match="ses modeli gerekli"):
        engine.ensure_available()


def test_model_dosyasi_bulunamazsa_kullanilamaz(tmp_path, ikili):
    engine = PiperEngine(
        replace(Config(), piper_binary=ikili, piper_model=tmp_path / "yok.onnx")
    )

    with pytest.raises(EngineUnavailable, match="bulunamadı"):
        engine.ensure_available()


def test_ikili_yoksa_kurulum_ipucu_verilir(model, monkeypatch):
    monkeypatch.setattr(piper_modulu.shutil, "which", lambda name: None)
    engine = PiperEngine(replace(Config(), piper_model=model))

    with pytest.raises(EngineUnavailable, match="uv tool install piper-tts"):
        engine.ensure_available()


def test_pathteki_ikili_kullanilir(model, monkeypatch):
    monkeypatch.setattr(piper_modulu.shutil, "which", lambda name: "/usr/bin/piper")
    engine = PiperEngine(replace(Config(), piper_model=model))

    engine.ensure_available()


def test_hazir_yapilandirma_gecerlidir(config):
    PiperEngine(config).ensure_available()


def test_metin_stdinden_verilir(config, calistirilan, tmp_path):
    engine = PiperEngine(config)

    asyncio.run(engine.synthesize("Merhaba dünya.", tmp_path / "ses.wav"))

    assert calistirilan.kayit["stdin"] == "Merhaba dünya.".encode("utf-8")


def test_model_ve_cikti_komuta_gecer(config, calistirilan, tmp_path):
    hedef = tmp_path / "ses.wav"

    asyncio.run(PiperEngine(config).synthesize("metin", hedef))

    command = calistirilan.kayit["command"]
    assert str(config.piper_model) in command
    assert str(hedef) in command


@pytest.mark.parametrize(
    ("rate", "beklenen"),
    [(1.0, "1.0000"), (1.15, "0.8696"), (2.0, "0.5000"), (0.5, "2.0000")],
)
def test_hiz_ters_orantili_uzunluga_cevrilir(config, calistirilan, tmp_path, rate, beklenen):
    """Piper hızı süre üzerinden ifade eder; hız arttıkça uzunluk azalmalı."""
    engine = PiperEngine(replace(config, rate=rate))

    asyncio.run(engine.synthesize("metin", tmp_path / "ses.wav"))

    command = calistirilan.kayit["command"]
    assert command[command.index("--length-scale") + 1] == beklenen


def test_gecersiz_hiz_hata_verir(config, calistirilan, tmp_path):
    engine = PiperEngine(replace(config, rate=0))

    with pytest.raises(EngineError, match="rate pozitif olmalı"):
        asyncio.run(engine.synthesize("metin", tmp_path / "ses.wav"))


def test_piper_hatasi_sarilir(config, calistirilan, tmp_path):
    calistirilan.ayar["returncode"] = 1
    calistirilan.ayar["stderr"] = b"model yuklenemedi"

    with pytest.raises(EngineError, match="model yuklenemedi"):
        asyncio.run(PiperEngine(config).synthesize("metin", tmp_path / "ses.wav"))


def test_bos_cikti_hata_verir(config, calistirilan, tmp_path):
    calistirilan.ayar["ciktiyi_yaz"] = False

    with pytest.raises(EngineError, match="boş ses dosyası"):
        asyncio.run(PiperEngine(config).synthesize("metin", tmp_path / "ses.wav"))


def test_cikti_wav_uzantilidir():
    assert PiperEngine.output_suffix == ".wav"
