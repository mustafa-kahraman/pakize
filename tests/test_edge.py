"""edge-tts motoru testleri.

Hermetiktir: ağa çıkılmaz, `edge_tts.Communicate` yamalanır.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from pakize.config import Config
from pakize.engines import EngineError, EngineUnavailable
from pakize.engines import edge as edge_modulu
from pakize.engines.edge import EdgeEngine


@pytest.fixture
def communicate(monkeypatch):
    """`Communicate` yerine, davranışı ayarlanabilir bir sahte koyar."""
    ayar = {"kurucu_hatasi": None, "kaydet_hatasi": None, "ciktiyi_yaz": True}
    kayit: dict = {}

    class SahteCommunicate:
        def __init__(self, text, voice, rate, volume, pitch):
            if ayar["kurucu_hatasi"] is not None:
                raise ayar["kurucu_hatasi"]
            kayit.update(text=text, voice=voice, rate=rate, volume=volume, pitch=pitch)

        async def save(self, path):
            if ayar["kaydet_hatasi"] is not None:
                raise ayar["kaydet_hatasi"]
            if ayar["ciktiyi_yaz"]:
                Path(path).write_bytes(b"sahte mp3")

    monkeypatch.setattr(edge_modulu.edge_tts, "Communicate", SahteCommunicate)
    return type("Kurulum", (), {"ayar": ayar, "kayit": kayit})


@pytest.fixture
def engine() -> EdgeEngine:
    return EdgeEngine(Config())


async def test_ayarlar_edge_tts_bicimine_cevrilir(engine, communicate, tmp_path):
    await engine.synthesize("Merhaba.", tmp_path / "ses.mp3")

    assert communicate.kayit["voice"] == "tr-TR-EmelNeural"
    assert communicate.kayit["rate"] == "+15%"
    assert communicate.kayit["volume"] == "+0%"
    assert communicate.kayit["pitch"] == "+0Hz"


async def test_kurucu_hatasi_da_sarilir(engine, communicate, tmp_path):
    """Geçersiz ses adında edge-tts kurucuda patlar.

    Sarmalanmazsa ham traceback dökülür ve yedek motora hiç geçilmez.
    """
    communicate.ayar["kurucu_hatasi"] = ValueError("Invalid voice 'yok'")

    with pytest.raises(EngineError, match="Invalid voice"):
        await engine.synthesize("metin", tmp_path / "ses.mp3")


async def test_kaydetme_hatasi_sarilir(engine, communicate, tmp_path):
    communicate.ayar["kaydet_hatasi"] = ConnectionError("ağ yok")

    with pytest.raises(EngineError, match="ağ yok"):
        await engine.synthesize("metin", tmp_path / "ses.mp3")


async def test_bos_cikti_hata_verir(engine, communicate, tmp_path):
    communicate.ayar["ciktiyi_yaz"] = False

    with pytest.raises(EngineError, match="boş ses dosyası"):
        await engine.synthesize("metin", tmp_path / "ses.mp3")


def test_sessiz_yapilandirma_kullanilamaz():
    engine = EdgeEngine(replace(Config(), voice=""))

    with pytest.raises(EngineUnavailable):
        engine.ensure_available()
