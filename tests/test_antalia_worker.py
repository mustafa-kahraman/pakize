"""antalia işçisinin saf mantığının testleri.

Hermetiktir: torch, numpy ve antalia_mini yoktur; model açılışı `sys.modules`'a
enjekte edilen sahte bir `antalia_mini` ile sınanır. Ses biçimleme
(`worker_audio`) EMA işçisi testlerinde ayrıntılı sınanır; burada antalia
işçisinin onu doğru parametrelerle çağırdığı ve çıktının sözleşmeye uyduğu
doğrulanır.
"""

import io
import json
import struct
import subprocess
import sys
import types
import wave
from pathlib import Path

import pytest

from pakize.engines import antalia_worker as isci
from pakize.engines import worker_audio as ses

REVIZYON = "1e8166a7436f3e11f7f03b339258ec30f366db60"
AKUSTIK_SHA = "72c36a6855ce95dc1d35960a7b61515136813313406e5b9ae1c2ebe6cd2ad428"
VOKODER_SHA = "89ca374cc55864b38a36f9ea87c41e1b17376e5d6d68e3a0458332861509bbf6"


# --- K2: sürüm, revizyon, sha256 ----------------------------------------------


def test_dogru_surum_kabul_edilir():
    isci.check_version("1.0.0")


@pytest.mark.parametrize("surum", ["0.9.0", "1.0.1", "1.1.0", "2.0.0"])
def test_baska_surum_reddedilir(surum):
    with pytest.raises(isci.SetupError) as hata:
        isci.check_version(surum)

    assert hata.value.code == "wrong_version"
    assert hata.value.as_message()["installed"] == surum


def test_paket_yoksa_reddedilir():
    with pytest.raises(isci.SetupError) as hata:
        isci.check_version(None)

    assert hata.value.code == "missing_package"


def test_kurulu_surum_paket_yoksa_none():
    assert isci.installed_version("boyle-bir-paket-yok-pakize") is None


def test_sabitler_incelenen_surumle_ayni():
    """Revizyon ve sha256'lar bilet incelemesindeki değerler; yanlışlıkla değişmesin."""
    assert isci.REQUIRED_VERSION == "1.0.0"
    assert isci.REPO_ID == "cloud0day3/antalia-mini"
    assert isci.REVISION == REVIZYON
    assert isci.CHECKSUMS == {
        "acoustic.safetensors": AKUSTIK_SHA,
        "vocoder.safetensors": VOKODER_SHA,
    }


def test_sha256_uyusmazsa_reddedilir(tmp_path):
    dosya = tmp_path / "acoustic.safetensors"
    dosya.write_bytes(b"kurcalanmis agirlik")

    with pytest.raises(isci.SetupError) as hata:
        isci.verify_checksum(dosya, "acoustic.safetensors")

    assert hata.value.code == "checksum_mismatch"
    assert hata.value.as_message()["file"] == "acoustic.safetensors"


def _surum_dizini(tmp_path, monkeypatch, bozuk: str | None = None) -> Path:
    """İki ağırlık dosyasını yazar; `bozuk` verilen dosyanın sha256'sı sabitle uyuşmaz."""
    dizin = tmp_path / "surum"
    dizin.mkdir(parents=True)
    for ad in isci.CHECKSUMS:
        dosya = dizin / ad
        if ad == bozuk:
            dosya.write_bytes(b"kurcalanmis agirlik")
        else:
            dosya.write_bytes(ad.encode())
            monkeypatch.setitem(isci.CHECKSUMS, ad, isci.sha256_of(dosya))
    return dizin


def test_iki_agirlik_dosyasi_da_dogrulanir(tmp_path, monkeypatch):
    isci.verify_release(_surum_dizini(tmp_path, monkeypatch))

    with pytest.raises(isci.SetupError) as hata:
        isci.verify_release(_surum_dizini(tmp_path / "b", monkeypatch, bozuk="vocoder.safetensors"))

    assert hata.value.code == "checksum_mismatch"
    assert hata.value.as_message()["file"] == "vocoder.safetensors"


@pytest.fixture
def sahte_antalia(monkeypatch, tmp_path):
    """`antalia_mini.Antalia` taklidi: kurucu argümanlarını kaydeder, sürüm dizinini gösterir."""
    kayit: dict = {"init": [], "hata": None}
    dizin = _surum_dizini(tmp_path, monkeypatch)

    class Antalia:
        def __init__(self, model=None, **kwargs):
            kayit["init"].append({"model": model, **kwargs})
            if kayit["hata"] is not None:
                raise kayit["hata"]
            self.path = dizin
            self.defaults = {"steps": 8, "cfg": 2.0, "speed": 0.95, "temperature": 0.6}

    paket = types.ModuleType("antalia_mini")
    paket.Antalia = Antalia
    monkeypatch.setitem(sys.modules, "antalia_mini", paket)
    monkeypatch.setattr(isci, "installed_version", lambda *a: "1.0.0")
    return types.SimpleNamespace(kayit=kayit, dizin=dizin)


def test_model_sabit_revizyonla_ve_isinmasiz_acilir(sahte_antalia):
    tts = isci.prepare_model()

    assert sahte_antalia.kayit["init"] == [
        {"model": None, "revision": REVIZYON, "warmup": False}
    ], "yalnız revision ve warmup verilmeli; gerisi paket varsayılanı"
    assert tts.path == sahte_antalia.dizin


def test_acilan_surumun_sha256si_uyusmazsa_hazir_olunmaz(sahte_antalia, monkeypatch):
    monkeypatch.setitem(isci.CHECKSUMS, "acoustic.safetensors", AKUSTIK_SHA)

    with pytest.raises(isci.SetupError) as hata:
        isci.prepare_model()

    assert hata.value.code == "checksum_mismatch"
    assert hata.value.as_message()["file"] == "acoustic.safetensors"


def test_model_hazirlanirken_once_surum_denetlenir(sahte_antalia, monkeypatch):
    monkeypatch.setattr(isci, "installed_version", lambda *a: "1.0.1")

    with pytest.raises(isci.SetupError) as hata:
        isci.prepare_model()

    assert hata.value.code == "wrong_version"
    assert sahte_antalia.kayit["init"] == []


def test_paket_ithal_edilemezse_missing_package(monkeypatch):
    monkeypatch.setattr(isci, "installed_version", lambda *a: "1.0.0")
    monkeypatch.setitem(sys.modules, "antalia_mini", None)  # ithal ImportError verir

    with pytest.raises(isci.SetupError) as hata:
        isci.prepare_model()

    assert hata.value.code == "missing_package"


@pytest.mark.parametrize(
    ("hata", "kod"),
    [
        (ImportError("No module named 'torch'"), "missing_package"),
        (OSError("ağ yok"), "download_failed"),
        (FileNotFoundError("config.json"), "download_failed"),
        (RuntimeError("bozuk ağırlık"), "load_failed"),
        (ValueError("checksum mismatch (paketin kendi denetimi)"), "load_failed"),
    ],
)
def test_acilis_hatalari_koda_cevrilir(sahte_antalia, hata, kod):
    sahte_antalia.kayit["hata"] = hata

    with pytest.raises(isci.SetupError) as sonuc:
        isci.prepare_model()

    assert sonuc.value.code == kod
    assert str(hata) in sonuc.value.detail


# --- K2: hız eşlemesi ----------------------------------------------------------


def test_hiz_bir_ise_paket_varsayilani_kullanilir():
    assert isci.speed_for(1.0, 0.95) is None


@pytest.mark.parametrize(("rate", "beklenen"), [(1.2, 1.14), (0.5, 0.475), (2.0, 1.9)])
def test_hiz_varsayilanla_carpilir(rate, beklenen):
    assert isci.speed_for(rate, 0.95) == pytest.approx(beklenen)


@pytest.mark.parametrize("rate", [0.0, -1.0])
def test_pozitif_olmayan_hiz_hata_verir(rate):
    with pytest.raises(ValueError):
        isci.speed_for(rate, 0.95)


# --- protokol ve çıktı (K3, K4) ---------------------------------------------------


class SahteTts:
    """`say` çağrılarını kaydeder; sabit bir ses dizisi döner."""

    def __init__(self, audio=(0.5, -0.25, 0.0), sample_rate: int = 48000) -> None:
        self.cagrilar: list[dict] = []
        self.audio = list(audio)
        self.sample_rate = sample_rate
        self.defaults = {"steps": 8, "cfg": 2.0, "speed": 0.95, "temperature": 0.6}

    def say(self, text, **kwargs):
        self.cagrilar.append({"text": text, **kwargs})
        if "PATLA" in text:
            raise RuntimeError("sentez patladı")
        return types.SimpleNamespace(audio=self.audio, sample_rate=self.sample_rate)


def _istek(**alanlar) -> bytes:
    return (json.dumps(alanlar) + "\n").encode("utf-8")


def _ornekler(path: Path) -> tuple[list[int], int]:
    with wave.open(str(path), "rb") as okuyucu:
        assert okuyucu.getnchannels() == 1
        assert okuyucu.getsampwidth() == 2
        pcm = okuyucu.readframes(okuyucu.getnframes())
        return list(struct.unpack(f"<{len(pcm) // 2}h", pcm)), okuyucu.getframerate()


def test_istek_kesmeyi_koruyarak_tohum_sifirla_seslendirilir(tmp_path):
    tts = SahteTts()
    kanal = io.StringIO()
    hedef = tmp_path / "00000.wav"
    metin = "EMA'nın README'ye eklenen %20'si, GitHub'a push edildi."

    isci.serve(tts, kanal, [_istek(text=metin, out=str(hedef), rate=1.0, volume=1.0)])

    assert kanal.getvalue() == '{"ok": true}\n'
    assert tts.cagrilar == [{"text": metin, "seed": 0, "speed": None}]


def test_hiz_bir_degilse_varsayilan_hizla_carpilir(tmp_path):
    tts = SahteTts()

    isci.serve(
        tts, io.StringIO(), [_istek(text="x", out=str(tmp_path / "a.wav"), rate=1.2, volume=1.0)]
    )

    assert tts.cagrilar[0]["speed"] == pytest.approx(0.95 * 1.2)
    assert tts.cagrilar[0]["seed"] == 0


UZUN = 3000
"""Sönüm penceresinden (720 örnek) uzun bir parça; başı sönümden etkilenmez."""


def test_cikti_normalize_sonumlu_kuyruklu_48khz_16bit(tmp_path):
    """K4: tepe 0.95 × volume, son 15 ms sıfıra iner, ardından 0,85 sn tam sıfır."""
    hedef = tmp_path / "a.wav"
    tts = SahteTts(audio=[0.5, -0.5] * (UZUN // 2))

    isci.serve(tts, io.StringIO(), [_istek(text="x", out=str(hedef), rate=1.0, volume=0.8)])

    ornekler, hiz = _ornekler(hedef)
    sessiz = ses.tail_silence_count()
    sonum = round(ses.FADE_OUT_SECONDS * 48000)
    assert hiz == 48000
    assert sessiz == 40800 and sonum == 720
    assert len(ornekler) == UZUN + sessiz
    assert max(ornekler) == round(0.95 * 0.8 * 32767), "tepe normalizasyonu × volume"
    assert ornekler[-sessiz:] == [0] * sessiz, "kuyruk tam sıfır olmalı"
    sesli = ornekler[:UZUN]
    assert sesli[-1] == 0, "sönüm sıfırda bitmeli"
    assert abs(sesli[-sonum - 1]) == round(0.95 * 0.8 * 32767), "sönüm penceresi dışı dokunulmaz"
    genlikler = [abs(d) for d in sesli[-sonum:]]
    assert all(a >= b for a, b in zip(genlikler, genlikler[1:])), "sönüm tekdüze azalmalı"


def test_cikti_saf_python_yoluyla_ayni_sozlesmeye_uyar(tmp_path):
    hedef = tmp_path / "a.wav"

    isci.serve(SahteTts(), io.StringIO(), [_istek(text="x", out=str(hedef), rate=1.0, volume=1.0)])

    ornekler, _ = _ornekler(hedef)
    assert len(ornekler) == 3 + ses.tail_silence_count()
    assert ornekler[:3] == list(
        struct.unpack("<3h", ses.to_pcm16(ses.shape_tail([0.95, -0.475, 0.0])[:3]))
    )


def test_modelin_ornekleme_hizi_wav_basligina_yazilir(tmp_path):
    hedef = tmp_path / "a.wav"

    isci.serve(
        SahteTts(sample_rate=24000),
        io.StringIO(),
        [_istek(text="x", out=str(hedef), rate=1.0, volume=1.0)],
    )

    ornekler, hiz = _ornekler(hedef)
    assert hiz == 24000
    assert len(ornekler) == 3 + ses.tail_silence_count(24000)


def test_sentez_hatasi_yanit_olarak_doner_isci_yasar(tmp_path):
    kanal = io.StringIO()
    istekler = [
        _istek(text="PATLA", out=str(tmp_path / "a.wav"), rate=1.0, volume=1.0),
        _istek(text="devam", out=str(tmp_path / "b.wav"), rate=1.0, volume=1.0),
    ]

    isci.serve(SahteTts(), kanal, istekler)

    satirlar = [json.loads(s) for s in kanal.getvalue().splitlines()]
    assert satirlar[0]["ok"] is False
    assert "sentez patladı" in satirlar[0]["error"]
    assert satirlar[1] == {"ok": True}


def test_pozitif_olmayan_hiz_istegi_reddedilir(tmp_path):
    kanal = io.StringIO()

    isci.serve(SahteTts(), kanal, [_istek(text="x", out=str(tmp_path / "a.wav"), rate=0, volume=1)])

    yanit = json.loads(kanal.getvalue())
    assert yanit["ok"] is False
    assert "positive" in yanit["error"]


def test_bos_satirlar_atlanir():
    kanal = io.StringIO()

    isci.serve(SahteTts(), kanal, [b"\n", b"   \n"])

    assert kanal.getvalue() == ""


BASLATICI = '''
import importlib.util, io, os, sys, types
spec = importlib.util.spec_from_file_location("antalia_worker", {worker!r})
isci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isci)

sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="cp1252", errors="backslashreplace", line_buffering=True)


class SahteTts:
    defaults = {{"speed": 0.95}}

    def say(self, text, *, seed, speed):
        print("torch gürültüsü: print üzerinden")
        os.write(1, b"C gurultusu: 1 numarali tanitici\\n")
        return types.SimpleNamespace(audio=[0.5, -0.5], sample_rate=48000)


def sahte_prepare_model():
    print("model yuklenirken gurultu")
    return SahteTts()


isci.prepare_model = sahte_prepare_model
sys.exit(isci.main())
'''


def test_gercek_isci_gurultuyu_protokol_akisina_karistirmaz(tmp_path):
    """Gerçek işçi kodu (`main`, `claim_stdout`, `serve`) `-I` ile alt süreçte çalışır;
    `worker_audio`'yu kendi dizininden bulabilmeli."""
    baslatici = tmp_path / "baslatici.py"
    baslatici.write_text(BASLATICI.format(worker=str(Path(isci.__file__))), encoding="utf-8")
    hedef = tmp_path / "parca.wav"
    istek = json.dumps({"text": "Merhaba", "out": str(hedef), "rate": 1.0, "volume": 1.0})

    sonuc = subprocess.run(
        [sys.executable, "-I", str(baslatici)],
        input=(istek + "\n").encode("utf-8"),
        capture_output=True,
        timeout=60,
    )

    assert sonuc.returncode == 0, sonuc.stderr.decode(errors="replace")
    satirlar = [json.loads(s) for s in sonuc.stdout.decode("utf-8").splitlines()]
    assert satirlar == [{"ready": True}, {"ok": True}]
    stderr = sonuc.stderr.decode("utf-8", errors="replace")
    assert "�" not in stderr, "stderr UTF-8 değil (Windows kod sayfası kalmış)"
    for gurultu in (
        "torch gürültüsü: print üzerinden",
        "C gurultusu: 1 numarali tanitici",
        "model yuklenirken gurultu",
    ):
        assert gurultu in stderr
    ornekler, hiz = _ornekler(hedef)
    assert hiz == 48000
    assert len(ornekler) == 2 + ses.tail_silence_count()


def test_gercek_isci_acilis_hatasini_protokolle_bildirir():
    """Paket yoksa `missing_package` satırı ve çıkış 1; `-I` ile `worker_audio` yine bulunur."""
    sonuc = subprocess.run(
        [sys.executable, "-I", str(Path(isci.__file__))],
        input=b"",
        capture_output=True,
        timeout=60,
    )

    assert sonuc.returncode == 1, sonuc.stderr.decode(errors="replace")
    satirlar = [json.loads(s) for s in sonuc.stdout.decode("utf-8").splitlines()]
    assert satirlar == [
        {"ready": False, "code": "missing_package", "error": "antalia-mini is not installed"}
    ]


def test_isci_pakizeyi_ithal_etmez():
    """Betik ayrı ortamda çalışır; orada `pakize` yoktur, göreli ithal de yoktur."""
    import ast

    kaynak = Path(isci.__file__).read_text(encoding="utf-8")
    ithaller = [
        n for n in ast.walk(ast.parse(kaynak)) if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    for node in ithaller:
        adlar = (
            [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
        )
        assert not any(ad.startswith("pakize") or ad == "" for ad in adlar), ast.dump(node)
        assert getattr(node, "level", 0) == 0, "göreli ithal yasak"


def test_ses_yardimcilari_pakizeyi_ithal_etmez():
    import ast

    kaynak = Path(ses.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(kaynak)):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("pakize"), ast.dump(node)
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("pakize") for a in node.names), ast.dump(node)
