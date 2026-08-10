"""Ses çalma ve durdurma testleri.

Hermetiktir: ffplay çalıştırılmaz, süreç nesnesi sahtelenir.
"""

import signal
from types import SimpleNamespace

import pytest

from pakize import audio
from pakize.audio import AudioError


class SahteSurec:
    """communicate/terminate arayüzünü taklit eden sahte ffplay süreci."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr
        self.terminate_edildi = False
        self.pid = 999_999

    def communicate(self):
        return (b"", self._stderr)

    def terminate(self):
        self.terminate_edildi = True


@pytest.fixture(autouse=True)
def temiz_kayit():
    """Her testten sonra modül düzeyindeki çalan süreç kaydını temizler."""
    yield
    audio._player = None


@pytest.fixture(autouse=True)
def sinyal_yakala(monkeypatch) -> list[tuple[int, int]]:
    """`os.kill`'i yamalar.

    Sahte süreç numarasına gerçek sinyal göndermek başka bir süreci
    vurabilirdi; testler asla gerçek sinyal göndermemeli.
    """
    gonderilen: list[tuple[int, int]] = []
    monkeypatch.setattr(audio.os, "kill", lambda pid, sig: gonderilen.append((pid, sig)))
    return gonderilen


@pytest.fixture
def surec(monkeypatch):
    """`subprocess.Popen`'ı sahte süreçle değiştirir."""
    tutucu = SimpleNamespace(son=None)

    def ayarla(returncode: int = 0, stderr: bytes = b""):
        def sahte_popen(command, **kwargs):
            tutucu.son = SahteSurec(returncode, stderr)
            return tutucu.son

        monkeypatch.setattr(audio.subprocess, "Popen", sahte_popen)
        monkeypatch.setattr(audio, "_require_binary", lambda name: f"/usr/bin/{name}")
        return tutucu

    return ayarla


def test_calma_basariliysa_hata_yok(surec, tmp_path):
    tutucu = surec()

    audio.play(tmp_path / "ses.mp3")

    assert tutucu.son is not None


def test_calma_bitince_kayit_temizlenir(surec, tmp_path):
    surec()

    audio.play(tmp_path / "ses.mp3")

    assert audio.stop_playback() is False


def test_sonlandirma_sinyali_hata_sayilmaz(surec, tmp_path):
    surec(returncode=-signal.SIGTERM)

    audio.play(tmp_path / "ses.mp3")


def test_gercek_hata_yukselir(surec, tmp_path):
    surec(returncode=1, stderr=b"kodek yok")

    with pytest.raises(AudioError, match="kodek yok"):
        audio.play(tmp_path / "ses.mp3")


def test_stop_playback_calan_sureci_sonlandirir(sinyal_yakala):
    sahte = SahteSurec()
    audio._set_player(sahte)

    assert audio.stop_playback() is True
    assert sahte.terminate_edildi is True
    # Duraklatılmış olma ihtimaline karşı, sonlandırmadan önce devam sinyali.
    assert sinyal_yakala == [(sahte.pid, signal.SIGCONT)]


def test_ayni_bicimdeki_parcalar_yeniden_kodlanmaz(tmp_path, monkeypatch):
    komutlar: list[list[str]] = []
    monkeypatch.setattr(audio, "_require_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(audio, "_run", lambda command: komutlar.append(command))

    parts = [tmp_path / "0.mp3", tmp_path / "1.mp3"]
    for part in parts:
        part.write_bytes(b"ses")

    audio.concat(parts, tmp_path / "cikti.mp3")

    assert "-c" in komutlar[0] and "copy" in komutlar[0]


def test_farkli_bicimdeki_parcalar_donusturulur(tmp_path, monkeypatch):
    """Piper WAV üretir; hedef .mp3 ise kopyalamak uzantısı yalan söyleyen
    bir dosya bırakırdı."""
    komutlar: list[list[str]] = []
    monkeypatch.setattr(audio, "_require_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(audio, "_run", lambda command: komutlar.append(command))

    parts = [tmp_path / "0.wav", tmp_path / "1.wav"]
    for part in parts:
        part.write_bytes(b"ses")

    audio.concat(parts, tmp_path / "cikti.mp3")

    assert "copy" not in komutlar[0]


def test_tek_wav_parca_da_mp3ye_donusturulur(tmp_path, monkeypatch):
    komutlar: list[list[str]] = []
    monkeypatch.setattr(audio, "_require_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(audio, "_run", lambda command: komutlar.append(command))

    part = tmp_path / "0.wav"
    part.write_bytes(b"ses")

    audio.concat([part], tmp_path / "cikti.mp3")

    # Kopyalama değil dönüştürme yapılmalı; ffmpeg çağrılmış olmalı.
    assert komutlar and "copy" not in komutlar[0]


def test_stop_playback_calan_yoksa_false():
    assert audio.stop_playback() is False


def test_olmus_surec_stop_playbackte_hata_vermez():
    class OlmusSurec(SahteSurec):
        def terminate(self):
            raise ProcessLookupError

    audio._set_player(OlmusSurec())

    assert audio.stop_playback() is False
