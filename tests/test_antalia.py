"""antalia motoru testleri.

Hermetiktir: torch ve antalia-mini yoktur. İşçi betiğinin yerine protokolü
taklit eden bir sahte betik `sys.executable` ile çalıştırılır. İşçi sürecin
ömrü (`worker.py`) EMA testlerinde derinlemesine sınanır; burada antalia'ya
özgü olan vardır: config anahtarı, kurulum mesajları, isteğin alanları ve
kesme işaretlerinin korunması.
"""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pakize import cli, pipeline
from pakize.config import Config, load_config, set_config_value
from pakize.engines import EngineError, EngineUnavailable, create_engine
from pakize.engines import antalia as antalia_modulu
from pakize.engines.antalia import AntaliaEngine
from pakize.engines.base import TtsEngine

KURULUM_KOMUTLARI = (
    "uv venv --python 3.12 ~/.local/share/pakize-antalia",
    "uv pip install --python ~/.local/share/pakize-antalia torch --index https://download.pytorch.org/whl/cpu",
    'uv pip install --python ~/.local/share/pakize-antalia "antalia-mini @ '
    "https://huggingface.co/cloud0day3/antalia-mini/resolve/"
    '1e8166a7436f3e11f7f03b339258ec30f366db60/antalia_mini-1.0.0-py3-none-any.whl"',
)
"""README'deki kurulum komutları, birebir."""

SAHTE_ISCI = '''
import json, os, sys
MODE = {mode!r}
KAYIT = {kayit!r}

with open(KAYIT, "a", encoding="utf-8") as kayit:
    kayit.write(json.dumps({{"pid": os.getpid(), "isolated": sys.flags.isolated}}) + "\\n")

if MODE == "acilista_ol":
    sys.stderr.write("ModuleNotFoundError: torch yok\\n")
    sys.exit(1)
if MODE == "surum_yanlis":
    print(json.dumps({{"ready": False, "code": "wrong_version", "installed": "1.0.1"}}), flush=True)
    sys.exit(1)
if MODE == "paket_yok":
    print(json.dumps({{"ready": False, "code": "missing_package", "error": "No module named 'antalia_mini'"}}), flush=True)
    sys.exit(1)
if MODE == "sha_uyusmaz":
    print(json.dumps({{"ready": False, "code": "checksum_mismatch", "file": "vocoder.safetensors"}}), flush=True)
    sys.exit(1)

print(json.dumps({{"ready": True}}), flush=True)
for raw in iter(sys.stdin.buffer.readline, b""):
    istek = json.loads(raw)
    if "PATLA" in istek["text"]:
        print(json.dumps({{"ok": False, "error": "sentez patladı"}}), flush=True)
        continue
    with open(istek["out"], "w", encoding="utf-8") as cikti:
        json.dump(istek, cikti, ensure_ascii=False)
    print(json.dumps({{"ok": True}}), flush=True)
'''


class SahteKurulum:
    def __init__(self, tmp_path: Path) -> None:
        self.dizin = tmp_path
        self.kayit = tmp_path / "baslatmalar.jsonl"

    def betik(self, mode: str = "normal") -> Path:
        path = self.dizin / f"sahte_isci_{mode}.py"
        path.write_text(SAHTE_ISCI.format(mode=mode, kayit=str(self.kayit)), encoding="utf-8")
        return path

    def baslatmalar(self) -> list[dict]:
        if not self.kayit.is_file():
            return []
        return [json.loads(s) for s in self.kayit.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def kurulum(tmp_path) -> SahteKurulum:
    return SahteKurulum(tmp_path)


@pytest.fixture
def config() -> Config:
    return replace(
        Config(), engine="antalia", fallback_engine=None, antalia_python=Path(sys.executable)
    )


def _motor(config: Config, kurulum: SahteKurulum, mode: str = "normal") -> AntaliaEngine:
    return AntaliaEngine(config, worker_path=kurulum.betik(mode))


def _seslendir(engine: AntaliaEngine, metin: str, hedef: Path) -> dict:
    async def senaryo():
        try:
            await engine.synthesize(metin, hedef)
        finally:
            await engine.aclose()

    asyncio.run(senaryo())
    return json.loads(hedef.read_text(encoding="utf-8"))


# --- K1: seçim ve kullanılabilirlik -------------------------------------------


def test_kayitli_motor_antalia(config):
    assert isinstance(create_engine("antalia", config), AntaliaEngine)
    assert AntaliaEngine.output_suffix == ".wav"


def test_python_yolu_bossa_kurulum_adimlari_soylenir():
    engine = AntaliaEngine(Config())

    with pytest.raises(EngineUnavailable, match="antalia_python") as hata:
        engine.ensure_available()

    mesaj = str(hata.value)
    for komut in KURULUM_KOMUTLARI:
        assert komut in mesaj
    assert 'antalia_python = "~/.local/share/pakize-antalia/bin/python"' in mesaj


def test_python_yolu_dosya_degilse_kullanilamaz(tmp_path):
    engine = AntaliaEngine(replace(Config(), antalia_python=tmp_path / "yok" / "python"))

    with pytest.raises(EngineUnavailable, match="antalia_python ile gösterilen Python yok"):
        engine.ensure_available()


def test_gecerli_yorumlayici_kabul_edilir_surec_acilmaz(config, kurulum):
    _motor(config, kurulum).ensure_available()

    assert kurulum.baslatmalar() == []


def test_config_dosyasindan_engine_ve_yol_okunur(tmp_path):
    path = tmp_path / "config.toml"
    set_config_value("engine", "antalia", path)
    set_config_value("antalia_python", "~/.local/share/pakize-antalia/bin/python", path)

    config = load_config(path)

    assert config.engine == "antalia"
    assert config.antalia_python == (
        Path.home() / ".local" / "share" / "pakize-antalia" / "bin" / "python"
    )


def test_cli_engine_bayragi_antaliayi_secer(monkeypatch, tmp_path):
    from pakize.pipeline import Plan, SpeechResult

    gorulen: dict = {}

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        gorulen["config"] = config
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)
    monkeypatch.setattr(cli, "_play_tone", lambda name, config: None)
    hedef = tmp_path / "ses.mp3"

    sonuc = CliRunner().invoke(
        cli.app, ["speak", "--engine", "antalia", "--no-play", "-o", str(hedef)], input="Merhaba.\n"
    )

    assert sonuc.exit_code == 0, sonuc.output
    assert gorulen["config"].engine == "antalia"


def test_config_set_fallback_engine_antaliayi_kabul_eder(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: path)

    sonuc = CliRunner().invoke(cli.app, ["config", "set", "fallback_engine", "antalia"])

    assert sonuc.exit_code == 0, sonuc.output
    assert load_config(path).fallback_engine == "antalia"


# --- istek -------------------------------------------------------------------


def test_istek_metni_hizi_sesi_ve_hedefi_tasir(config, kurulum, tmp_path):
    engine = _motor(replace(config, rate=1.2, volume=0.8), kurulum)
    hedef = tmp_path / "a.wav"

    istek = _seslendir(engine, "Merhaba dünya.", hedef)

    assert istek == {"text": "Merhaba dünya.", "out": str(hedef), "rate": 1.2, "volume": 0.8}


def test_isciye_giden_metinde_kesme_isaretleri_korunur(config, kurulum, tmp_path):
    """K3: antalia kesmeyi kendi çözüyor; EMA'nın temizliği burada uygulanmaz."""
    metin = "EMA'nın README'ye eklenen %20'si, GitHub'a push edildi. Ali’nin ‘evi’."

    istek = _seslendir(_motor(config, kurulum), metin, tmp_path / "a.wav")

    assert istek["text"] == metin


def test_pozitif_olmayan_hiz_isci_acilmadan_hata_verir(config, kurulum, tmp_path):
    engine = _motor(replace(config, rate=0.0), kurulum)

    with pytest.raises(EngineError, match="rate pozitif olmalı"):
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert kurulum.baslatmalar() == []


def test_parcalar_tek_izole_isciyle_seslendirilir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum)
    hedefler = [tmp_path / f"{i:05d}.wav" for i in range(4)]

    async def senaryo():
        await asyncio.gather(
            *(engine.synthesize(f"Parça {i}.", hedef) for i, hedef in enumerate(hedefler))
        )
        surec = engine._worker.process
        await engine.aclose()
        return surec

    surec = asyncio.run(senaryo())

    assert all(h.is_file() for h in hedefler)
    assert len(kurulum.baslatmalar()) == 1
    assert kurulum.baslatmalar()[0]["isolated"] == 1
    assert surec.returncode is not None, "aclose işçiyi kapatmadı"


# --- açılış hataları -----------------------------------------------------------


def test_isci_hata_satiri_verirse_engine_error(config, kurulum, tmp_path):
    with pytest.raises(EngineError, match="antalia seslendirme başarısız: sentez patladı"):
        _seslendir(_motor(config, kurulum), "PATLA", tmp_path / "a.wav")


def test_isci_acilista_olurse_engine_unavailable_ve_stderr_kuyrugu(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="acilista_ol")

    with pytest.raises(EngineUnavailable, match="antalia işçisi açılırken kapandı") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert "torch yok" in str(hata.value)


def test_surum_yanlissa_kurulum_komutu_soylenir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="surum_yanlis")

    with pytest.raises(EngineUnavailable, match="antalia-mini 1.0.1 kurulu") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    mesaj = str(hata.value)
    assert "1.0.0" in mesaj
    assert f'uv pip install --python {sys.executable} "antalia-mini @ ' in mesaj


def test_paket_eksikse_ayri_ortam_onerilir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="paket_yok")

    with pytest.raises(EngineUnavailable, match="No module named 'antalia_mini'") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    mesaj = str(hata.value)
    for komut in KURULUM_KOMUTLARI:
        assert komut in mesaj
    assert f"--python {sys.executable}" not in mesaj


def test_sha256_uyusmazsa_dosya_adi_soylenir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="sha_uyusmaz")

    with pytest.raises(EngineUnavailable, match="antalia model dosyası beklenen sha256") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert "vocoder.safetensors" in str(hata.value)


def test_kurulum_komutlari_readme_ile_birebir():
    assert antalia_modulu.install_steps(antalia_modulu.ENV_DIR_EXAMPLE).splitlines() == [
        f"  {komut}" for komut in KURULUM_KOMUTLARI
    ]


# --- boru hattıyla birlikte --------------------------------------------------


class SahteBirincil(TtsEngine):
    """Her zaman kullanılamayan birincil motor; yedeğe geçişi tetikler."""

    name = "sahte"

    def ensure_available(self) -> None:
        raise EngineUnavailable("sahte motor yok")

    async def synthesize(self, text: str, destination: Path) -> None:
        raise AssertionError("birincil motor çağrılmamalı")


@pytest.fixture
def motorlar(monkeypatch, kurulum):
    ornekler: dict[str, TtsEngine] = {}

    def sahte_create(name: str, cfg: Config):
        if name == "antalia":
            ornekler[name] = AntaliaEngine(cfg, worker_path=kurulum.betik())
        else:
            ornekler[name] = SahteBirincil(cfg)
        return ornekler[name]

    monkeypatch.setattr(pipeline, "create_engine", sahte_create)

    def concat(parts: list[Path], destination: Path) -> Path:
        destination.write_bytes(b"\n".join(p.read_bytes() for p in parts))
        return destination

    monkeypatch.setattr(pipeline, "concat", concat)
    return ornekler


def test_yedek_motor_antalia_birincil_dusunce_devreye_girer(config, kurulum, motorlar, tmp_path):
    config = replace(config, engine="sahte", fallback_engine="antalia", max_chunk_chars=20)
    hedef = tmp_path / "ses.wav"

    sonuc = pipeline.synthesize("Birinci cümle. İkinci cümle.", hedef, config)

    assert sonuc.engine == "antalia"
    assert len(sonuc.plan.chunks) == 2
    assert len(kurulum.baslatmalar()) == 1
    assert motorlar["antalia"]._worker is None, "iş bitince işçi kapanmalı"
