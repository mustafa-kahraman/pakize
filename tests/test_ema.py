"""EMA motoru testleri.

Hermetiktir: torch ve EMA yoktur. İşçi betiğinin yerine, protokolü taklit
eden bir sahte betik `sys.executable` ile çalıştırılır. Böylece süreç ömrü
(tek işçi, kapanış, iptal) ve hata yolları gerçek alt süreçlerle sınanır.
"""

import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pakize import pipeline
from pakize.config import Config
from pakize.engines import EngineError, EngineUnavailable, create_engine
from pakize.engines import ema as ema_modulu
from pakize.engines import worker as isci_modulu
from pakize.engines.base import TtsEngine
from pakize.engines.ema import EmaEngine

SAHTE_ISCI = '''
import io, json, os, sys, time
MODE = {mode!r}
KAYIT = {kayit!r}
BEKLEME_ISARETI = {isaret!r}

# Windows'ta stderr yerel kod sayfasıyla açılır; bunu her platformda taklit
# edip gerçek işçinin yaptığı gibi UTF-8'e alırız (ema_worker.utf8_stderr).
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="cp1252", errors="backslashreplace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Her başlatma kaydedilir: testler süreç sayısını ve -I bayrağını buradan okur.
with open(KAYIT, "a", encoding="utf-8") as kayit:
    kayit.write(json.dumps({{"pid": os.getpid(), "isolated": sys.flags.isolated}}) + "\\n")

sys.stderr.write("torch gürültüsü: uyarı falan\\n")

if MODE == "acilista_ol":
    sys.stderr.write("ModuleNotFoundError: torch yok\\n")
    sys.exit(1)
if MODE == "surum_yanlis":
    print(json.dumps({{"ready": False, "code": "wrong_version", "installed": "1.0.2"}}), flush=True)
    sys.exit(1)
if MODE == "paket_yok":
    print(json.dumps({{"ready": False, "code": "missing_package", "error": "No module named 'torch'"}}), flush=True)
    sys.exit(1)

print(json.dumps({{"ready": True}}), flush=True)
for raw in iter(sys.stdin.buffer.readline, b""):
    istek = json.loads(raw)
    metin = istek["text"]
    if "PATLA" in metin:
        print(json.dumps({{"ok": False, "error": "sentez patladı"}}), flush=True)
        continue
    if "BEKLE" in metin:
        open(BEKLEME_ISARETI, "w").close()
        time.sleep(60)
    if "ÖL" in metin:
        sys.stderr.write("segfault gibi bir şey\\n")
        sys.exit(3)
    with open(istek["out"], "w", encoding="utf-8") as cikti:
        json.dump(istek, cikti, ensure_ascii=False)
    print(json.dumps({{"ok": True}}), flush=True)
'''


class SahteKurulum:
    """Sahte işçi betiğini ve başlatma kaydını bir arada tutar."""

    def __init__(self, tmp_path: Path) -> None:
        self.dizin = tmp_path
        self.kayit = tmp_path / "baslatmalar.jsonl"
        self.bekleme_isareti = tmp_path / "bekliyor"

    def betik(self, mode: str = "normal") -> Path:
        path = self.dizin / f"sahte_isci_{mode}.py"
        path.write_text(
            SAHTE_ISCI.format(
                mode=mode, kayit=str(self.kayit), isaret=str(self.bekleme_isareti)
            ),
            encoding="utf-8",
        )
        return path

    def baslatmalar(self) -> list[dict]:
        if not self.kayit.is_file():
            return []
        return [json.loads(s) for s in self.kayit.read_text(encoding="utf-8").splitlines()]

    async def isci_beklemeye_gecsin(self) -> None:
        for _ in range(400):
            if self.bekleme_isareti.exists():
                return
            await asyncio.sleep(0.025)
        raise AssertionError("sahte işçi bekleme isteğini almadı")


@pytest.fixture
def kurulum(tmp_path) -> SahteKurulum:
    return SahteKurulum(tmp_path)


@pytest.fixture
def config() -> Config:
    return replace(Config(), engine="ema", fallback_engine=None, ema_python=Path(sys.executable))


def _motor(config: Config, kurulum: SahteKurulum, mode: str = "normal") -> EmaEngine:
    return EmaEngine(config, worker_path=kurulum.betik(mode))


# --- kullanılabilirlik -------------------------------------------------------


def test_python_yolu_bossa_kurulum_adimlari_soylenir():
    engine = EmaEngine(Config())

    with pytest.raises(EngineUnavailable, match="ema_python") as hata:
        engine.ensure_available()

    assert "ema-lightning==1.0.1" in str(hata.value)
    assert f"uv venv --python 3.12 {ema_modulu.ENV_DIR_EXAMPLE}" in str(hata.value)


def test_python_yolu_dosya_degilse_kullanilamaz(tmp_path):
    engine = EmaEngine(replace(Config(), ema_python=tmp_path / "yok" / "python"))

    with pytest.raises(EngineUnavailable, match="Python yok"):
        engine.ensure_available()


def test_gecerli_yorumlayici_kabul_edilir(config):
    EmaEngine(config).ensure_available()


def test_kullanilabilirlik_denetimi_surec_acmaz(config, kurulum):
    _motor(config, kurulum).ensure_available()

    assert kurulum.baslatmalar() == []


def test_kayitli_motor_ema(config):
    assert isinstance(create_engine("ema", config), EmaEngine)
    assert EmaEngine.output_suffix == ".wav"


# --- tek işçi, çok parça -----------------------------------------------------


def test_parcalar_tek_isciyle_seslendirilir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum)
    hedefler = [tmp_path / f"{i:05d}.wav" for i in range(5)]

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
    assert surec.returncode is not None, "aclose işçiyi kapatmadı"


def test_isci_izole_kipte_calistirilir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum)

    async def senaryo():
        await engine.synthesize("metin", tmp_path / "a.wav")
        await engine.aclose()

    asyncio.run(senaryo())

    assert kurulum.baslatmalar()[0]["isolated"] == 1


def test_istek_hiz_ses_ve_hedefi_tasir(config, kurulum, tmp_path):
    engine = _motor(replace(config, rate=1.15, volume=0.8), kurulum)
    hedef = tmp_path / "a.wav"

    async def senaryo():
        await engine.synthesize("Merhaba dünya.", hedef)
        await engine.aclose()

    asyncio.run(senaryo())

    istek = json.loads(hedef.read_text(encoding="utf-8"))
    assert istek == {"text": "Merhaba dünya.", "out": str(hedef), "speed": 1.15, "volume": 0.8}


def test_isciye_giden_istekte_kesme_isareti_yok(config, kurulum, tmp_path):
    """EMA'nın düzenleyicisi kesmeyi sesli okuyor; motor onu göndermeden temizler."""
    engine = _motor(config, kurulum)
    hedef = tmp_path / "a.wav"

    async def senaryo():
        await engine.synthesize("EMA’nın README'ye %20'si.", hedef)
        await engine.aclose()

    asyncio.run(senaryo())

    istek = json.loads(hedef.read_text(encoding="utf-8"))
    assert istek["text"] == "EMA nın README ye %20 si."
    assert not any(k in istek["text"] for k in "'’‘ʼ´`")


def test_hic_baslamamis_motoru_kapatmak_sorunsuz(config, kurulum):
    asyncio.run(_motor(config, kurulum).aclose())

    assert kurulum.baslatmalar() == []


def test_aralik_disi_hiz_isci_acilmadan_hata_verir(config, kurulum, tmp_path):
    engine = _motor(replace(config, rate=5.0), kurulum)

    with pytest.raises(EngineError, match="0.25 ile 4.0 arasında"):
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert kurulum.baslatmalar() == []


# --- hatalar -----------------------------------------------------------------


def test_isci_hata_satiri_verirse_engine_error(config, kurulum, tmp_path):
    engine = _motor(config, kurulum)

    async def senaryo():
        try:
            await engine.synthesize("PATLA", tmp_path / "a.wav")
        finally:
            await engine.aclose()

    with pytest.raises(EngineError, match="sentez patladı"):
        asyncio.run(senaryo())


def test_isci_acilista_olurse_engine_unavailable_ve_stderr_kuyrugu(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="acilista_ol")

    with pytest.raises(EngineUnavailable, match="çıkış kodu 1") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert "torch yok" in str(hata.value)


def test_surum_yanlissa_kurulum_komutu_soylenir(config, kurulum, tmp_path):
    engine = _motor(config, kurulum, mode="surum_yanlis")

    with pytest.raises(EngineUnavailable, match="1.0.2") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert "ema-lightning==1.0.1" in str(hata.value)
    assert str(sys.executable) in str(hata.value)


def test_paket_eksikse_ayri_ortam_onerilir(config, kurulum, tmp_path):
    """Gösterilen Python sistem Python'u olabilir; torch'u oraya kurmayı önermemeli."""
    engine = _motor(config, kurulum, mode="paket_yok")

    with pytest.raises(EngineUnavailable, match="No module named 'torch'") as hata:
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    mesaj = str(hata.value)
    assert f"uv venv --python 3.12 {ema_modulu.ENV_DIR_EXAMPLE}" in mesaj
    assert f"--python {ema_modulu.ENV_DIR_EXAMPLE} " in mesaj
    assert f"--python {sys.executable}" not in mesaj


def test_ortam_komutu_python_surumunu_sabitler():
    """ema-lightning 1.0.1 Python ≥ 3.11 ister; uv 3.10'a düşerse kurulum kalıyordu."""
    assert "--python 3.12" in ema_modulu.VENV_COMMAND
    assert ema_modulu.VENV_COMMAND.startswith("uv venv ")


def test_kurulum_komutu_cpu_torch_dizinini_tek_dizin_olarak_verir():
    """`--index-url` + `--extra-index-url` ikilisi uv'de CUDA torch kurduruyordu."""
    komut = ema_modulu.INSTALL_COMMAND

    assert "--index https://download.pytorch.org/whl/cpu" in komut
    assert "--extra-index-url" not in komut
    assert "--index-url" not in komut
    assert "ema-lightning==1.0.1" in komut


def test_isci_ust_surec_olunce_kapanacak_sekilde_baslatilir(config, kurulum, tmp_path, monkeypatch):
    """`die_with_parent` alt sürece `preexec_fn` olarak verilmeli (kill -9 güvencesi).

    Gerçek süreç açılmaz: Windows `preexec_fn`'i hiç kabul etmez, Linux'ta da
    sahte bir fonksiyonu çocukta çalıştırmaya gerek yok. Kaydedici argümanları
    alır ve başlatmayı bir OSError ile keser; motor bunu EngineUnavailable yapar.
    """
    kayit: dict = {}

    def isaret() -> None:
        return None

    async def kaydeden_exec(*command, **kwargs):
        kayit["command"] = list(command)
        kayit["kwargs"] = kwargs
        raise OSError("kayıt alındı, süreç açılmadı")

    monkeypatch.setattr(isci_modulu, "die_with_parent", lambda: isaret)
    monkeypatch.setattr(isci_modulu.asyncio, "create_subprocess_exec", kaydeden_exec)
    engine = _motor(config, kurulum)

    with pytest.raises(EngineUnavailable, match="süreç açılmadı"):
        asyncio.run(engine.synthesize("metin", tmp_path / "a.wav"))

    assert kayit["kwargs"].get("preexec_fn") is isaret
    assert kayit["command"][:2] == [sys.executable, "-I"]
    assert kurulum.baslatmalar() == []


def test_yanit_gecikirse_isci_kapatilir_ve_hata_verilir(config, kurulum, tmp_path, monkeypatch):
    """Takılan işçi Pakize'yi sonsuza dek bekletmemeli."""
    monkeypatch.setattr(isci_modulu, "REQUEST_TIMEOUT_BASE", 0.3)
    monkeypatch.setattr(isci_modulu, "REQUEST_SECONDS_PER_CHAR", 0.0)
    monkeypatch.setattr(isci_modulu, "STOP_GRACE_SECONDS", 0.2)
    engine = _motor(config, kurulum)

    async def senaryo():
        try:
            await engine.synthesize("BEKLE", tmp_path / "a.wav")
        finally:
            surec = engine._worker.process if engine._worker else None
            await engine.aclose()
        return surec

    with pytest.raises(EngineError, match="0 sn içinde yanıt vermedi") as hata:
        asyncio.run(senaryo())

    assert "kapatıldı" in str(hata.value)
    assert kurulum.bekleme_isareti.exists(), "işçi isteği almış olmalı"


def test_zaman_asimi_hatasi_kibar_kapanisi_beklemez(config, kurulum, tmp_path, monkeypatch):
    """Takılmış işçi stdin'i okumaz; hata STOP_GRACE_SECONDS kadar gecikmemeli."""
    import time

    monkeypatch.setattr(isci_modulu, "REQUEST_TIMEOUT_BASE", 0.3)
    monkeypatch.setattr(isci_modulu, "REQUEST_SECONDS_PER_CHAR", 0.0)
    monkeypatch.setattr(isci_modulu, "STOP_GRACE_SECONDS", 30.0)
    engine = _motor(config, kurulum)

    async def senaryo():
        basla = time.monotonic()
        with pytest.raises(EngineError, match="yanıt vermedi"):
            await engine.synthesize("BEKLE", tmp_path / "a.wav")
        return time.monotonic() - basla

    gecen = asyncio.run(senaryo())

    assert gecen < 5.0, f"hata {gecen:.1f} sn gecikti; kibar kapanış beklenmiş"


def test_zaman_asimi_mesajina_stderr_kuyrugu_eklenir(config, kurulum, tmp_path, monkeypatch):
    monkeypatch.setattr(isci_modulu, "REQUEST_TIMEOUT_BASE", 0.3)
    monkeypatch.setattr(isci_modulu, "REQUEST_SECONDS_PER_CHAR", 0.0)
    engine = _motor(config, kurulum)

    with pytest.raises(EngineError, match="yanıt vermedi") as hata:
        asyncio.run(engine.synthesize("BEKLE", tmp_path / "a.wav"))

    assert "torch gürültüsü: uyarı falan" in str(hata.value)


def test_yanit_zaman_asimi_isci_surecini_oldurur(config, kurulum, tmp_path, monkeypatch):
    monkeypatch.setattr(isci_modulu, "REQUEST_TIMEOUT_BASE", 0.3)
    monkeypatch.setattr(isci_modulu, "REQUEST_SECONDS_PER_CHAR", 0.0)
    monkeypatch.setattr(isci_modulu, "STOP_GRACE_SECONDS", 0.2)
    engine = _motor(config, kurulum)
    surecler: list = []

    async def senaryo():
        gorev = asyncio.create_task(engine.synthesize("BEKLE", tmp_path / "a.wav"))
        await kurulum.isci_beklemeye_gecsin()
        surecler.append(engine._worker.process)
        with pytest.raises(EngineError):
            await gorev

    asyncio.run(senaryo())

    assert surecler[0].returncode is not None


def test_yanit_suresi_parca_uzunluguyla_buyur():
    assert isci_modulu.request_timeout("") == pytest.approx(60.0)
    assert isci_modulu.request_timeout("x" * 2500) == pytest.approx(310.0)


def test_acilis_hatasi_tekrar_isci_acmaz(config, kurulum, tmp_path):
    """Kilidi bekleyen parçalar aynı hatayı almalı; her biri yeni süreç açmamalı."""
    engine = _motor(config, kurulum, mode="acilista_ol")

    async def senaryo():
        sonuclar = await asyncio.gather(
            *(engine.synthesize(f"p{i}", tmp_path / f"{i}.wav") for i in range(4)),
            return_exceptions=True,
        )
        await engine.aclose()
        return sonuclar

    sonuclar = asyncio.run(senaryo())

    assert all(isinstance(s, EngineUnavailable) for s in sonuclar)
    assert len(kurulum.baslatmalar()) == 1


def test_isci_seslendirme_sirasinda_olurse_engine_error(config, kurulum, tmp_path):
    engine = _motor(config, kurulum)

    async def senaryo():
        try:
            await engine.synthesize("ÖL", tmp_path / "a.wav")
        finally:
            await engine.aclose()

    with pytest.raises(EngineError, match="seslendirme sırasında kapandı") as hata:
        asyncio.run(senaryo())

    assert "segfault gibi" in str(hata.value)


# --- boru hattıyla birlikte --------------------------------------------------


class SahteYedek(TtsEngine):
    name = "sahte"
    output_suffix = ".txt"

    def ensure_available(self) -> None:
        return None

    async def synthesize(self, text: str, destination: Path) -> None:
        destination.write_text(text, encoding="utf-8")


@pytest.fixture
def motorlar(monkeypatch, kurulum):
    """`create_engine`'i sahte işçili EMA'ya ve metin yazan yedeğe yönlendirir."""
    ornekler: dict[str, TtsEngine] = {}
    secenekler = {"mode": "normal"}

    def sahte_create(name: str, cfg: Config):
        if name == "ema":
            ornekler[name] = EmaEngine(cfg, worker_path=kurulum.betik(secenekler["mode"]))
        else:
            ornekler[name] = SahteYedek(cfg)
        return ornekler[name]

    monkeypatch.setattr(pipeline, "create_engine", sahte_create)

    def concat(parts: list[Path], destination: Path) -> Path:
        destination.write_bytes(b"\n".join(p.read_bytes() for p in parts))
        return destination

    monkeypatch.setattr(pipeline, "concat", concat)
    return type("Kurulum", (), {"ornekler": ornekler, "secenekler": secenekler})


def test_boru_hatti_cok_parcayi_tek_isciyle_birlestirir(config, kurulum, motorlar, tmp_path):
    config = replace(config, max_chunk_chars=20)
    hedef = tmp_path / "ses.wav"

    sonuc = pipeline.synthesize("Birinci cümle. İkinci cümle. Üçüncü cümle.", hedef, config)

    assert sonuc.engine == "ema"
    assert len(sonuc.plan.chunks) == 3
    assert len(kurulum.baslatmalar()) == 1
    icerik = hedef.read_text(encoding="utf-8")
    assert icerik.index("Birinci") < icerik.index("İkinci") < icerik.index("Üçüncü")
    assert motorlar.ornekler["ema"]._worker is None, "iş bitince işçi kapanmalı"


def test_boru_hatti_hatada_isciyi_kapatir(config, kurulum, motorlar, tmp_path):
    with pytest.raises(EngineError, match="sentez patladı"):
        pipeline.synthesize("Bu parça PATLA.", tmp_path / "ses.wav", config)

    assert motorlar.ornekler["ema"]._worker is None


def test_isci_acilamazsa_yedek_motora_gecilir(config, kurulum, motorlar, tmp_path):
    motorlar.secenekler["mode"] = "acilista_ol"
    config = replace(config, fallback_engine="sahte")

    sonuc = pipeline.synthesize("Kısa bir metin.", tmp_path / "ses.txt", config)

    assert sonuc.engine == "sahte"
    assert len(kurulum.baslatmalar()) == 1


def test_iptal_edilince_isci_kapanir(config, kurulum, motorlar, tmp_path):
    """Ctrl+C karşılığı: boru hattı iptal edilince alt süreç geride kalmamalı."""

    async def senaryo():
        gorev = asyncio.create_task(
            pipeline.synthesize_async("Burada BEKLE.", tmp_path / "ses.wav", config)
        )
        await kurulum.isci_beklemeye_gecsin()
        surec = motorlar.ornekler["ema"]._worker.process
        gorev.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gorev
        return surec

    surec = asyncio.run(senaryo())

    assert surec.returncode is not None
    assert motorlar.ornekler["ema"]._worker is None


def test_kapanis_bekleyen_isciyi_oldurur(config, kurulum, tmp_path, monkeypatch):
    """stdin kapanınca çıkmayan işçi, süre dolunca öldürülür."""
    monkeypatch.setattr(isci_modulu, "STOP_GRACE_SECONDS", 0.2)
    engine = _motor(config, kurulum)

    async def senaryo():
        gorev = asyncio.create_task(engine.synthesize("BEKLE", tmp_path / "a.wav"))
        await kurulum.isci_beklemeye_gecsin()
        surec = engine._worker.process
        gorev.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gorev
        await engine.aclose()
        return surec

    surec = asyncio.run(senaryo())

    assert surec.returncode is not None
    assert surec.returncode != 0
