"""EMA işçisinin saf mantığının testleri.

Hermetiktir: torch, numpy, ema_lightning ve huggingface_hub yoktur; güvenli
yükleyici `sys.modules`'a enjekte edilen sahte modüllerle sınanır. İşçi betiği
`pakize`'yi ithal etmez ama Pakize onu bir modül olarak ithal edebilir —
ağır kütüphaneler yalnızca fonksiyon içinde ithal edildiği için.
"""

import io
import json
import sys
import types
import wave
from pathlib import Path

import pytest

from pakize.engines import ema_worker as isci


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
    assert isci.gain_for(0.5, 1.0) == pytest.approx(1.9)
    assert isci.normalize([0.5, -0.25], 1.0) == pytest.approx([0.95, -0.475])


def test_volume_ile_carpilir():
    assert isci.normalize([0.5], 0.5) == pytest.approx([0.475])


def test_asan_degerler_kirpilir():
    sonuc = isci.normalize([0.5, -0.5], 2.0)

    assert sonuc == [1.0, -1.0]


def test_sessiz_parcada_sifira_bolme_olmaz():
    assert isci.gain_for(0.0, 1.0) == 0.0
    assert isci.normalize([0.0, 0.0], 1.0) == [0.0, 0.0]
    assert isci.normalize([], 1.0) == []


def test_pcm16_donusumu():
    assert isci.to_pcm16([0.0, 1.0, -1.0]) == b"\x00\x00\xff\x7f\x01\x80"


def test_render_pcm_numpysiz_calisir():
    pcm = isci.render_pcm([0.5, -0.5], 1.0)

    assert pcm == isci.to_pcm16([0.95, -0.95])


def test_wav_48khz_mono_16bit(tmp_path):
    hedef = tmp_path / "parca.wav"

    isci.write_wav(hedef, isci.to_pcm16([0.1, 0.2, 0.3]))

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
        assert okuyucu.readframes(3) == isci.to_pcm16([0.95, -0.475, 0.0])


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
