"""Boru hattı testleri.

Tamamen hermetiktir: TTS motoru sahtedir, ağ erişimi yoktur, ffmpeg yerine
`audio.concat` yamalanır. Testler ağ ve harici ikili olmadan da geçer.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from pakize import pipeline
from pakize.config import Config
from pakize.engines import EngineError, EngineUnavailable
from pakize.engines.base import TtsEngine
from pakize.models import Action, SegmentType

ORNEK_METIN = """# Kurulum

Önce bağımlılıkları kur.

```bash
uv sync
uv run pakize speak notlar.md
```

Sonra `pakize config` ile ayarlara bak.
"""


class SahteMotor(TtsEngine):
    """Metni sese değil, düz metin dosyasına yazan test motoru."""

    name = "sahte"
    output_suffix = ".txt"

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.cagrilar: list[str] = []

    def ensure_available(self) -> None:
        return None

    async def synthesize(self, text: str, destination: Path) -> None:
        self.cagrilar.append(text)
        destination.write_text(text, encoding="utf-8")


class BozukMotor(SahteMotor):
    name = "bozuk"

    def ensure_available(self) -> None:
        raise EngineUnavailable("bu motor yok")


@pytest.fixture
def motorlar(monkeypatch):
    """`create_engine`'i sahte motorlara yönlendirir ve örnekleri sunar."""
    ornekler: dict[str, SahteMotor] = {}
    siniflar = {"sahte": SahteMotor, "bozuk": BozukMotor}

    def sahte_create(name: str, config: Config):
        if name not in siniflar:
            raise EngineError(f"Bilinmeyen motor: {name!r}")
        ornekler[name] = siniflar[name](config)
        return ornekler[name]

    monkeypatch.setattr(pipeline, "create_engine", sahte_create)
    return ornekler


@pytest.fixture
def sahte_concat(monkeypatch):
    """ffmpeg yerine parçaları metin olarak birleştirir."""

    def concat(parts: list[Path], destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "\n".join(p.read_text(encoding="utf-8") for p in parts), encoding="utf-8"
        )
        return destination

    monkeypatch.setattr(pipeline, "concat", concat)


@pytest.fixture
def config() -> Config:
    return replace(Config(), engine="sahte", fallback_engine=None)


def test_plan_kod_blogunu_anons_eder(config):
    plan = pipeline.plan_speech(ORNEK_METIN, config)
    metin = "\n".join(chunk.text for chunk in plan.chunks)

    assert "uv sync" not in metin
    assert "Burada 2 satırlık bir Bash kod bloğu var." in metin
    assert plan.skipped == {SegmentType.CODE_BLOCK: 1}


def test_plan_kod_atlama_politikasina_uyar(config):
    config = replace(
        config, policy={**config.policy, SegmentType.CODE_BLOCK: Action.SKIP}
    )

    plan = pipeline.plan_speech(ORNEK_METIN, config)
    metin = "\n".join(chunk.text for chunk in plan.chunks)

    assert "kod bloğu" not in metin
    assert "Kurulum." in metin


def test_synthesize_dosya_uretir(tmp_path, config, motorlar, sahte_concat):
    hedef = tmp_path / "ses.txt"

    sonuc = pipeline.synthesize(ORNEK_METIN, hedef, config)

    assert hedef.is_file()
    assert sonuc.engine == "sahte"
    assert sonuc.output == hedef
    assert "uv sync" not in hedef.read_text(encoding="utf-8")


def test_uzun_metin_birden_cok_parcaya_bolunur(tmp_path, config, motorlar, sahte_concat):
    config = replace(config, max_chunk_chars=60)
    metin = " ".join(f"Bu {i}. cümledir." for i in range(40))

    sonuc = pipeline.synthesize(metin, tmp_path / "ses.txt", config)

    assert len(sonuc.plan.chunks) > 1
    assert len(motorlar["sahte"].cagrilar) == len(sonuc.plan.chunks)


def test_parcalar_sirayi_koruyarak_birlestirilir(
    tmp_path, config, motorlar, sahte_concat
):
    config = replace(config, max_chunk_chars=30)
    metin = "Birinci cümle. İkinci cümle. Üçüncü cümle."

    hedef = pipeline.synthesize(metin, tmp_path / "ses.txt", config).output
    icerik = hedef.read_text(encoding="utf-8")

    assert icerik.index("Birinci") < icerik.index("İkinci") < icerik.index("Üçüncü")


def test_ilerleme_geri_cagrisi_tetiklenir(tmp_path, config, motorlar, sahte_concat):
    config = replace(config, max_chunk_chars=30)
    adimlar: list[tuple[int, int]] = []

    sonuc = pipeline.synthesize(
        "Birinci cümle. İkinci cümle. Üçüncü cümle.",
        tmp_path / "ses.txt",
        config,
        progress=lambda done, total: adimlar.append((done, total)),
    )

    toplam = len(sonuc.plan.chunks)
    assert len(adimlar) == toplam
    assert sorted(adim[0] for adim in adimlar) == list(range(1, toplam + 1))


def test_birincil_motor_calismazsa_yedege_dusulur(
    tmp_path, config, motorlar, sahte_concat
):
    config = replace(config, engine="bozuk", fallback_engine="sahte")

    sonuc = pipeline.synthesize("Kısa bir metin.", tmp_path / "ses.txt", config)

    assert sonuc.engine == "sahte"


def test_yedek_yoksa_hata_yukselir(tmp_path, config, motorlar, sahte_concat):
    config = replace(config, engine="bozuk", fallback_engine=None)

    with pytest.raises(EngineUnavailable):
        pipeline.synthesize("Kısa bir metin.", tmp_path / "ses.txt", config)


def test_tamamen_atlanan_metin_anlamli_hata_verir(
    tmp_path, config, motorlar, sahte_concat
):
    config = replace(
        config, policy={**config.policy, SegmentType.CODE_BLOCK: Action.SKIP}
    )

    with pytest.raises(EngineError, match="Seslendirilecek içerik kalmadı"):
        pipeline.synthesize("```py\nx = 1\n```", tmp_path / "ses.txt", config)


def test_motor_ag_hatasinda_yedege_dusulur(tmp_path, config, monkeypatch, sahte_concat):
    class AgKopukMotor(SahteMotor):
        name = "kopuk"

        async def synthesize(self, text: str, destination: Path) -> None:
            raise EngineError("bağlantı yok")

    siniflar = {"kopuk": AgKopukMotor, "sahte": SahteMotor}
    monkeypatch.setattr(
        pipeline, "create_engine", lambda name, cfg: siniflar[name](cfg)
    )
    config = replace(config, engine="kopuk", fallback_engine="sahte")

    sonuc = pipeline.synthesize("Kısa bir metin.", tmp_path / "ses.txt", config)

    assert sonuc.engine == "sahte"
