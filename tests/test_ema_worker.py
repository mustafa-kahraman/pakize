"""EMA işçisinin saf mantığının testleri.

Hermetiktir: torch, numpy, ema_lightning ve huggingface_hub yoktur; güvenli
yükleyici `sys.modules`'a enjekte edilen sahte modüllerle sınanır. İşçi betiği
`pakize`'yi ithal etmez ama Pakize onu bir modül olarak ithal edebilir —
ağır kütüphaneler yalnızca fonksiyon içinde ithal edildiği için.
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

from pakize.engines import ema_worker as isci
from pakize.engines import worker_audio as ses


# --- sürüm denetimi -----------------------------------------------------------


def test_dogru_surum_kabul_edilir():
    isci.check_version("1.0.1")


@pytest.mark.parametrize("surum", ["1.0.0", "1.0.2", "1.1.0", "2.0.0"])
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


# --- metin hazırlığı: kesme işaretleri ---------------------------------------


@pytest.mark.parametrize("kesme", list("'\u2019\u2018\u02bc\u00b4`"))
def test_her_kesme_varyanti_bosluk_olur(kesme):
    assert isci.prepare_text(f"EMA{kesme}nın") == "EMA nın"


def test_kesmeler_ornek_cumlelerde_cikar():
    assert isci.prepare_text("README'ye bak, %20'si 1990'lı.") == "README ye bak, %20 si 1990 lı."
    assert isci.prepare_text("2026'da") == "2026 da"  # bilinen bedel: ek ayrılır


def test_art_arda_bosluklar_teke_iner():
    assert isci.prepare_text("a ' b '' c") == "a b c"


def test_kesmesiz_metin_degismez():
    assert isci.prepare_text("Merhaba dünya.\nİkinci satır.") == "Merhaba dünya.\nİkinci satır."


# --- sha256 ------------------------------------------------------------------


def test_sha256_uyusmazsa_reddedilir(tmp_path):
    dosya = tmp_path / "ema.pt"
    dosya.write_bytes(b"kurcalanmis model")

    with pytest.raises(isci.SetupError) as hata:
        isci.verify_checksum(dosya, "ema.pt")

    assert hata.value.code == "checksum_mismatch"
    assert hata.value.as_message()["file"] == "ema.pt"


def test_sha256_uyusursa_gecer(tmp_path, monkeypatch):
    dosya = tmp_path / "config.json"
    dosya.write_bytes(b"{}")
    monkeypatch.setitem(isci.CHECKSUMS, "config.json", isci.sha256_of(dosya))

    isci.verify_checksum(dosya, "config.json")


def test_model_dosyalari_sabit_revizyondan_indirilir(tmp_path, monkeypatch):
    cagrilar: list[tuple] = []

    def sahte_indir(repo_id, filename, *, revision):
        cagrilar.append((repo_id, filename, revision))
        yerel = tmp_path / filename
        yerel.write_bytes(filename.encode())
        monkeypatch.setitem(isci.CHECKSUMS, filename, isci.sha256_of(yerel))
        return str(yerel)

    dosyalar = isci.fetch_model_files(sahte_indir)

    assert set(dosyalar) == {"ema.pt", "decoder.pt", "config.json"}
    assert all(revizyon == isci.REVISION for _, _, revizyon in cagrilar)
    assert all(repo == "canberkkkkkk/ema-lightning" for repo, _, _ in cagrilar)


def test_indirilen_dosya_bozuksa_yuklenmez(tmp_path):
    def sahte_indir(repo_id, filename, *, revision):
        yerel = tmp_path / filename
        yerel.write_bytes(b"baska icerik")
        return str(yerel)

    with pytest.raises(isci.SetupError) as hata:
        isci.fetch_model_files(sahte_indir)

    assert hata.value.code == "checksum_mismatch"


def test_indirme_hatasi_sarilir():
    def sahte_indir(repo_id, filename, *, revision):
        raise OSError("ağ yok")

    with pytest.raises(isci.SetupError) as hata:
        isci.fetch_model_files(sahte_indir)

    assert hata.value.code == "download_failed"
    assert "ağ yok" in hata.value.detail


# --- ses normalizasyonu ------------------------------------------------------


def test_tepe_hedefe_cekilir():
    assert ses.gain_for(0.5, 1.0) == pytest.approx(1.9)
    assert ses.normalize([0.5, -0.25], 1.0) == pytest.approx([0.95, -0.475])


def test_volume_ile_carpilir():
    assert ses.normalize([0.5], 0.5) == pytest.approx([0.475])


def test_asan_degerler_kirpilir():
    sonuc = ses.normalize([0.5, -0.5], 2.0)

    assert sonuc == [1.0, -1.0]


def test_sessiz_parcada_sifira_bolme_olmaz():
    assert ses.gain_for(0.0, 1.0) == 0.0
    assert ses.normalize([0.0, 0.0], 1.0) == [0.0, 0.0]
    assert ses.normalize([], 1.0) == []


def test_pcm16_donusumu():
    assert ses.to_pcm16([0.0, 1.0, -1.0]) == b"\x00\x00\xff\x7f\x01\x80"


def _ornekler(pcm: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(pcm) // 2}h", pcm))


def test_render_pcm_numpysiz_calisir():
    pcm = ses.render_pcm([0.5, -0.5], 1.0)

    # Son 15 ms sönümlenir: iki örneklik parçada ilki yarıya iner, ikincisi sıfırlanır;
    # ardından TAIL_SILENCE_SECONDS kadar sessizlik gelir.
    ornekler = _ornekler(pcm)
    assert ornekler[:2] == [round(0.95 * 0.5 * 32767), 0]
    assert len(ornekler) == 2 + ses.tail_silence_count()


class SahteDizi:
    """numpy dizisinin, `render_pcm`'in kullandığı kadarını taklit eder."""

    def __init__(self, degerler) -> None:
        self.degerler = [float(d) for d in degerler]

    @property
    def size(self) -> int:
        return len(self.degerler)

    def reshape(self, *_shape) -> "SahteDizi":
        return self

    def __getitem__(self, dilim: slice) -> "SahteDizi":
        return SahteDizi(self.degerler[dilim])

    def __mul__(self, carpan) -> "SahteDizi":
        if isinstance(carpan, SahteDizi):
            assert len(carpan.degerler) == len(self.degerler), "eleman sayısı uyuşmuyor"
            return SahteDizi([d * k for d, k in zip(self.degerler, carpan.degerler)])
        return SahteDizi([d * carpan for d in self.degerler])

    def max(self) -> float:
        return max(self.degerler)

    def round(self) -> "SahteDizi":
        return SahteDizi([round(d) for d in self.degerler])

    def astype(self, dtype: str) -> "SahteDizi":
        assert dtype == "<i2"
        for d in self.degerler:
            assert -32768 <= d <= 32767, f"16 bit taşması: {d} (kırpma yapılmamış)"
        return self

    def tobytes(self) -> bytes:
        return struct.pack(f"<{len(self.degerler)}h", *(int(d) for d in self.degerler))


@pytest.fixture
def sahte_numpy(monkeypatch):
    np = types.ModuleType("numpy")
    np.float32 = "float32"
    np.asarray = lambda a, dtype=None: SahteDizi(a)
    np.abs = lambda a: SahteDizi([abs(d) for d in a.degerler])
    np.clip = lambda a, lo, hi: SahteDizi([min(hi, max(lo, d)) for d in a.degerler])
    np.zeros = lambda n, dtype=None: SahteDizi([0.0] * n)
    np.concatenate = lambda diziler: SahteDizi([d for dizi in diziler for d in dizi.degerler])
    monkeypatch.setitem(sys.modules, "numpy", np)
    return np


UZUN = 3000
"""Sönüm penceresinden (720 örnek) uzun bir test parçası; baş kısmı sönümden etkilenmez."""


def test_numpy_yolu_volume_ile_carpar(sahte_numpy):
    assert _ornekler(ses.render_pcm([0.5] * UZUN, 0.5))[0] == round(0.475 * 32767)
    assert _ornekler(ses.render_pcm([0.5, -0.25] * UZUN, 1.0))[:2] == [
        round(0.95 * 32767),
        round(-0.475 * 32767),
    ]


def test_numpy_yolu_asan_degerleri_kirpar(sahte_numpy):
    assert _ornekler(ses.render_pcm([0.5, -0.5] * UZUN, 2.0))[:2] == [32767, -32767]


def test_numpy_yolu_sessiz_parcada_sifira_bolmez(sahte_numpy):
    sessiz = ses.tail_silence_count()
    assert _ornekler(ses.render_pcm([0.0, 0.0], 1.0)) == [0] * (2 + sessiz)
    assert _ornekler(ses.render_pcm([], 1.0)) == [0] * sessiz


def test_torch_tensoru_numpy_dizisine_cevrilir(sahte_numpy):
    class SahteTensor:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return [0.5]

    assert _ornekler(ses.render_pcm(SahteTensor(), 1.0))[0] == 0  # tek örnek: sönüm sıfırlar


# --- parça sonu: sönüm ve sessizlik -------------------------------------------


def _parca_sonu_dogrula(ornekler: list[int], orijinal_uzunluk: int) -> None:
    """Üç koruma: kuyruk tam sessizlik, tekdüze sönüm ve sıfırda biten ses, uzunluk."""
    sessiz = ses.tail_silence_count()
    sonum = int(round(ses.FADE_OUT_SECONDS * ses.SAMPLE_RATE))
    assert sessiz == round(ses.TAIL_SILENCE_SECONDS * ses.SAMPLE_RATE)
    assert sonum == round(ses.FADE_OUT_SECONDS * ses.SAMPLE_RATE)

    assert len(ornekler) == orijinal_uzunluk + sessiz
    assert ornekler[-sessiz:] == [0] * sessiz, "kuyruk tam sıfır olmalı"

    sesli = ornekler[:orijinal_uzunluk]
    assert sesli[-1] == 0, "son sesli örnek sıfıra inmeli"
    sonum_bolgesi = sesli[-sonum:]
    assert all(a >= b for a, b in zip(sonum_bolgesi, sonum_bolgesi[1:])), "sönüm tekdüze azalmalı"
    assert sonum_bolgesi[0] > sonum_bolgesi[-1]
    assert sesli[-sonum - 1] == round(0.95 * 32767), "sönüm penceresi dışı dokunulmaz"


def test_saf_python_yolu_parca_sonunu_bicimler():
    ornekler = _ornekler(ses.render_pcm([0.5] * UZUN, 1.0))

    _parca_sonu_dogrula(ornekler, UZUN)


def test_numpy_yolu_parca_sonunu_bicimler(sahte_numpy):
    ornekler = _ornekler(ses.render_pcm([0.5] * UZUN, 1.0))

    _parca_sonu_dogrula(ornekler, UZUN)


@pytest.mark.parametrize("uzunluk", [0, 1, 10, 719])
def test_sonumden_kisa_parca_cokmez(uzunluk):
    ornekler = _ornekler(ses.render_pcm([0.5] * uzunluk, 1.0))

    assert len(ornekler) == uzunluk + ses.tail_silence_count()
    if uzunluk:
        assert ornekler[uzunluk - 1] == 0
    assert ornekler[uzunluk:] == [0] * ses.tail_silence_count()


@pytest.mark.parametrize("uzunluk", [0, 1, 10, 719])
def test_sonumden_kisa_parca_numpy_yolunda_cokmez(sahte_numpy, uzunluk):
    ornekler = _ornekler(ses.render_pcm([0.5] * uzunluk, 1.0))

    assert len(ornekler) == uzunluk + ses.tail_silence_count()


def test_kuyruk_sessizligi_edge_kuyrugu_kadar_ve_tam_ornek():
    """Dinleme testi 0.85 sn'de karar kıldı; 48 kHz'de bu tam 40800 örnek, yuvarlama payı yok."""
    assert ses.TAIL_SILENCE_SECONDS == 0.85
    assert ses.FADE_OUT_SECONDS == 0.015
    assert ses.tail_silence_count() == 40800
    assert ses.tail_silence_count(24000) == 20400


def test_sonum_carpanlari_birden_sifira_iner():
    gains = ses.fade_out_gains(UZUN)

    assert len(gains) == 720
    assert gains[0] == pytest.approx(1.0, abs=0.01)
    assert gains[-1] == 0.0
    assert all(a > b for a, b in zip(gains, gains[1:]))
    assert ses.fade_out_gains(5) and len(ses.fade_out_gains(5)) == 5
    assert ses.fade_out_gains(0) == []


def test_sessiz_parcada_son_bicimleme_de_sessiz_kalir():
    ornekler = _ornekler(ses.render_pcm([0.0] * UZUN, 1.0))

    assert ornekler == [0] * (UZUN + ses.tail_silence_count())


def test_wav_48khz_mono_16bit(tmp_path):
    hedef = tmp_path / "parca.wav"

    ses.write_wav(hedef, ses.to_pcm16([0.1, 0.2, 0.3]))

    with wave.open(str(hedef), "rb") as okuyucu:
        assert okuyucu.getframerate() == 48000
        assert okuyucu.getnchannels() == 1
        assert okuyucu.getsampwidth() == 2
        assert okuyucu.getnframes() == 3


# --- hız eşlemesi ------------------------------------------------------------


@pytest.mark.parametrize("rate", [0.25, 1.0, 1.15, 4.0])
def test_hiz_oldugu_gibi_gecer(rate):
    assert isci.speed_from_rate(rate) == rate


@pytest.mark.parametrize("rate", [0.0, 0.1, 4.01, 10.0])
def test_aralik_disi_hiz_hata_verir(rate):
    with pytest.raises(ValueError):
        isci.speed_from_rate(rate)


# --- güvenli yükleme ---------------------------------------------------------


@pytest.fixture
def sahte_kutuphaneler(monkeypatch):
    """Sahte torch ve ema_lightning modüllerini `sys.modules`'a koyar."""
    yuklemeler: list[dict] = []

    torch = types.ModuleType("torch")

    def tehlikeli_load(path, map_location=None, **kwargs):
        # Gerçek paket böyle çağırır: weights_only=False. Sarmalayıcı ezmeli.
        yuklemeler.append({"path": path, **kwargs})
        return {"vocab": ["a", "b"]}

    torch.load = tehlikeli_load
    torch.device = lambda name: f"device:{name}"

    paket = types.ModuleType("ema_lightning")
    model = types.ModuleType("ema_lightning.model")
    decoder = types.ModuleType("ema_lightning.decoder")
    api = types.ModuleType("ema_lightning.api")
    frontend = types.ModuleType("ema_lightning.frontend")

    model.torch = torch
    decoder.torch = torch

    class Akustik:
        vocab = ["a", "b"]

    def load_acoustic(path, device):
        model.torch.load(path, map_location=device, weights_only=False)
        return Akustik()

    def load_decoder(path, device):
        decoder.torch.load(path, map_location=device, weights_only=False)
        return "decoder"

    model.load_acoustic = load_acoustic
    decoder.load_decoder = load_decoder

    class EMA:
        @classmethod
        def _from_parts(cls, acoustic, dec, fe, device):
            return ("ema", acoustic, dec, fe, device)

    api.EMA = EMA
    frontend.Frontend = lambda vocab: ("frontend", tuple(vocab))

    paket.model, paket.decoder, paket.api, paket.frontend = model, decoder, api, frontend
    for ad, modul in {
        "torch": torch,
        "ema_lightning": paket,
        "ema_lightning.model": model,
        "ema_lightning.decoder": decoder,
        "ema_lightning.api": api,
        "ema_lightning.frontend": frontend,
    }.items():
        monkeypatch.setitem(sys.modules, ad, modul)

    return types.SimpleNamespace(torch=torch, yuklemeler=yuklemeler, orijinal_load=tehlikeli_load)


def test_torch_load_her_zaman_weights_only_ile_cagrilir(sahte_kutuphaneler, tmp_path):
    tts = isci.safe_load_model(tmp_path / "ema.pt", tmp_path / "decoder.pt")

    yuklemeler = sahte_kutuphaneler.yuklemeler
    assert len(yuklemeler) == 2
    assert all(y["weights_only"] is True for y in yuklemeler)
    assert {Path(y["path"]).name for y in yuklemeler} == {"ema.pt", "decoder.pt"}
    assert tts[0] == "ema" and tts[3] == ("frontend", ("a", "b"))


def test_yukleme_bitince_torch_load_eski_haline_doner(sahte_kutuphaneler, tmp_path):
    isci.safe_load_model(tmp_path / "ema.pt", tmp_path / "decoder.pt")

    assert sahte_kutuphaneler.torch.load is sahte_kutuphaneler.orijinal_load


def test_yukleme_hata_verse_de_torch_load_geri_alinir(sahte_kutuphaneler, tmp_path):
    def patla(path, device):
        raise RuntimeError("bozuk dosya")

    sys.modules["ema_lightning.model"].load_acoustic = patla

    with pytest.raises(RuntimeError, match="bozuk dosya"):
        isci.safe_load_model(tmp_path / "ema.pt", tmp_path / "decoder.pt")

    assert sahte_kutuphaneler.torch.load is sahte_kutuphaneler.orijinal_load


def test_model_hazirlanirken_once_surum_denetlenir(monkeypatch):
    """Yanlış sürüm, paket eksikliğinden (huggingface_hub yok) önce yakalanmalı."""
    monkeypatch.setattr(isci, "installed_version", lambda *a: "1.0.2")

    with pytest.raises(isci.SetupError) as hata:
        isci.prepare_model()

    assert hata.value.code == "wrong_version"


def test_surum_dogruysa_eksik_kutuphane_bildirilir(monkeypatch):
    monkeypatch.setattr(isci, "installed_version", lambda *a: "1.0.1")
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # ithal ImportError verir

    with pytest.raises(isci.SetupError) as hata:
        isci.prepare_model()

    assert hata.value.code == "missing_package"


# --- protokol ----------------------------------------------------------------


class SahteTts:
    """`say` çağrılarını kaydeder; sabit bir ses dizisi döner."""

    def __init__(self) -> None:
        self.cagrilar: list[dict] = []

    def say(self, text, *, speed, seed, sample_rate):
        self.cagrilar.append(
            {"text": text, "speed": speed, "seed": seed, "sample_rate": sample_rate}
        )
        if "PATLA" in text:
            raise RuntimeError("sentez patladı")
        return types.SimpleNamespace(audio=[0.5, -0.25, 0.0], sample_rate=sample_rate)


def _istek(**alanlar) -> bytes:
    return (json.dumps(alanlar) + "\n").encode("utf-8")


def test_istek_seslendirilir_ve_wav_yazilir(tmp_path):
    tts = SahteTts()
    kanal = io.StringIO()
    hedef = tmp_path / "00000.wav"

    isci.serve(
        tts, kanal, [_istek(text="Merhaba", out=str(hedef), speed=1.15, volume=1.0)]
    )

    assert kanal.getvalue() == '{"ok": true}\n'
    assert tts.cagrilar == [
        {"text": "Merhaba", "speed": 1.15, "seed": 0, "sample_rate": 48000}
    ]
    with wave.open(str(hedef), "rb") as okuyucu:
        assert okuyucu.getframerate() == 48000
        assert okuyucu.getnframes() == 3 + ses.tail_silence_count()
        # Üç örneklik parça baştan sona sönüm penceresinde: 0.95·g0, -0.475·g1, 0.
        beklenen = ses.shape_tail([0.95, -0.475, 0.0])[:3]
        assert okuyucu.readframes(3) == ses.to_pcm16(beklenen)


def test_sentez_hatasi_yanit_olarak_doner_isci_yasar(tmp_path):
    kanal = io.StringIO()
    istekler = [
        _istek(text="PATLA", out=str(tmp_path / "a.wav"), speed=1.0, volume=1.0),
        _istek(text="devam", out=str(tmp_path / "b.wav"), speed=1.0, volume=1.0),
    ]

    isci.serve(SahteTts(), kanal, istekler)

    satirlar = [json.loads(s) for s in kanal.getvalue().splitlines()]
    assert satirlar[0]["ok"] is False
    assert "sentez patladı" in satirlar[0]["error"]
    assert satirlar[1] == {"ok": True}


def test_aralik_disi_hiz_istegi_reddedilir(tmp_path):
    kanal = io.StringIO()

    isci.serve(
        SahteTts(), kanal, [_istek(text="x", out=str(tmp_path / "a.wav"), speed=9, volume=1)]
    )

    yanit = json.loads(kanal.getvalue())
    assert yanit["ok"] is False
    assert "range" in yanit["error"]


def test_bos_satirlar_atlanir(tmp_path):
    kanal = io.StringIO()

    isci.serve(SahteTts(), kanal, [b"\n", b"   \n"])

    assert kanal.getvalue() == ""


def test_kurulum_hatasi_mesaji_kodu_tasir():
    hata = isci.SetupError("wrong_version", "ayrıntı", installed="1.0.2")

    assert hata.as_message() == {
        "ready": False,
        "code": "wrong_version",
        "error": "ayrıntı",
        "installed": "1.0.2",
    }


BASLATICI = '''
import importlib.util, io, os, sys, types
spec = importlib.util.spec_from_file_location("ema_worker", {worker!r})
isci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isci)

# Windows'un yerel kod sayfası taklidi: stderr cp1252 ile açılmış gibi.
# İşçi bunu claim_stdout içinde UTF-8'e almalı; almazsa Türkçe bozulur.
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="cp1252", errors="backslashreplace", line_buffering=True)


class SahteTts:
    def say(self, text, *, speed, seed, sample_rate):
        print("torch gürültüsü: print üzerinden")      # sys.stdout
        os.write(1, b"C gurultusu: 1 numarali tanitici\\n")  # fd 1
        return types.SimpleNamespace(audio=[0.5, -0.5], sample_rate=sample_rate)


def sahte_prepare_model():
    print("model yuklenirken gurultu")
    os.write(1, b"acilista fd gurultusu\\n")
    return SahteTts()


isci.prepare_model = sahte_prepare_model
sys.exit(isci.main())
'''


def test_gercek_isci_gurultuyu_protokol_akisina_karistirmaz(tmp_path):
    """Gerçek işçi kodu (`main`, `claim_stdout`, `serve`) alt süreçte çalışır.

    Model yerine sahte bir TTS verilir; o hem `print` ile hem 1 numaralı
    tanıtıcıya doğrudan yazarak gürültü üretir. stdout'ta yalnızca protokol
    satırları kalmalı, gürültü stderr'e gitmeli.
    """
    baslatici = tmp_path / "baslatici.py"
    baslatici.write_text(BASLATICI.format(worker=str(Path(isci.__file__))), encoding="utf-8")
    hedef = tmp_path / "parca.wav"
    istek = json.dumps({"text": "Merhaba", "out": str(hedef), "speed": 1.0, "volume": 1.0})

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
    assert "\ufffd" not in stderr, "stderr UTF-8 değil (Windows kod sayfası kalmış)"
    for gurultu in (
        "torch gürültüsü: print üzerinden",
        "C gurultusu: 1 numarali tanitici",
        "model yuklenirken gurultu",
        "acilista fd gurultusu",
    ):
        assert gurultu in stderr
    with wave.open(str(hedef), "rb") as okuyucu:
        assert okuyucu.getnframes() == 2 + ses.tail_silence_count()
        assert okuyucu.readframes(2) == ses.to_pcm16(ses.shape_tail([0.95, -0.95])[:2])


def test_gercek_isci_acilis_hatasini_protokolle_bildirir(tmp_path):
    """Sürüm denetimi gerçek işçide: paket yoksa `missing_package` satırı ve çıkış 1."""
    sonuc = subprocess.run(
        [sys.executable, "-I", str(Path(isci.__file__))],
        input=b"",
        capture_output=True,
        timeout=60,
    )

    assert sonuc.returncode == 1
    satirlar = [json.loads(s) for s in sonuc.stdout.decode("utf-8").splitlines()]
    assert len(satirlar) == 1
    assert satirlar[0]["ready"] is False
    assert satirlar[0]["code"] == "missing_package"


def test_isci_pakizeyi_ithal_etmez():
    """Betik ayrı ortamda çalışır; orada `pakize` yoktur."""
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
