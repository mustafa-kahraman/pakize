"""Duraklatma/sürdürme testleri.

Hermetiktir: gerçek süreçlere sinyal gönderilmez, `/proc` okuması ve `os.kill`
yamalanır.
"""

import signal

import pytest
from typer.testing import CliRunner

from pakize import cli, runtime

runner = CliRunner()

SPEAK_PID = 4242


@pytest.fixture
def surecler(monkeypatch):
    """Sahte bir süreç ağacı kurar ve gönderilen sinyalleri kaydeder."""
    gonderilen: list[tuple[int, int]] = []
    durumlar: dict[int, str] = {}

    def ayarla(**player_states: str):
        durumlar.clear()
        durumlar.update({int(pid): state for pid, state in player_states.items()})
        monkeypatch.setattr(
            runtime,
            "_players",
            lambda pid: [(p, s) for p, s in durumlar.items()] if pid == SPEAK_PID else [],
        )

    def sahte_kill(pid: int, sig: int) -> None:
        gonderilen.append((pid, sig))

    monkeypatch.setattr(runtime.os, "kill", sahte_kill)
    ayarla()
    return type("Kurulum", (), {"ayarla": staticmethod(ayarla), "gonderilen": gonderilen})


def test_calan_surec_duraklatilir(surecler):
    surecler.ayarla(**{"5001": "S"})

    assert runtime.pause(SPEAK_PID) is True
    assert surecler.gonderilen == [(5001, signal.SIGSTOP)]


def test_duraklatilmis_surec_surdurulur(surecler):
    surecler.ayarla(**{"5001": "T"})

    assert runtime.resume(SPEAK_PID) is True
    assert surecler.gonderilen == [(5001, signal.SIGCONT)]


def test_calan_yoksa_duraklatma_false_doner(surecler):
    surecler.ayarla()

    assert runtime.pause(SPEAK_PID) is False
    assert surecler.gonderilen == []


def test_duraklatilmislik_durumdan_okunur(surecler):
    surecler.ayarla(**{"5001": "T"})
    assert runtime.is_paused(SPEAK_PID) is True

    surecler.ayarla(**{"5001": "S"})
    assert runtime.is_paused(SPEAK_PID) is False


def test_calan_yokken_duraklatilmis_sayilmaz(surecler):
    surecler.ayarla()

    assert runtime.is_paused(SPEAK_PID) is False


def test_stat_ayristirmasi_bosluklu_komut_adini_kaldirir():
    satir = "5001 (ff play) T 4242 5001 0 0 -1 4194304 100 0 0"

    assert runtime._parse_stat_line(satir) == ("ff play", "T", 4242)


def test_bozuk_stat_satiri_none_doner():
    assert runtime._parse_stat_line("bozuk içerik") is None


def test_duraklat_komutu_calani_duraklatir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: SPEAK_PID)
    monkeypatch.setattr(cli.runtime, "is_paused", lambda pid: False)
    monkeypatch.setattr(cli.runtime, "pause", lambda pid: True)

    sonuc = runner.invoke(cli.app, ["duraklat"])

    assert sonuc.exit_code == 0
    assert "Duraklatıldı." in sonuc.stdout


def test_duraklat_komutu_duraklatilmisi_surdurur(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: SPEAK_PID)
    monkeypatch.setattr(cli.runtime, "is_paused", lambda pid: True)
    monkeypatch.setattr(cli.runtime, "resume", lambda pid: True)

    sonuc = runner.invoke(cli.app, ["duraklat"])

    assert sonuc.exit_code == 0
    assert "Devam ediyor." in sonuc.stdout


def test_duraklat_calan_yoksa_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: None)

    sonuc = runner.invoke(cli.app, ["duraklat"])

    assert sonuc.exit_code == 1
    assert "Çalan bir seslendirme yok." in sonuc.stdout


def test_durdurma_once_devam_ettirip_sonra_sonlandirir(monkeypatch):
    """Sıra kritik: SIGCONT sonlandırmadan ÖNCE gitmeli.

    Ters sırada ffplay bekleyen SIGTERM'i yutup çalmayı sürdürüyor; gerçek
    süreçlerle doğrulandı.
    """
    from pakize import audio

    gonderilen: list[tuple[int, int]] = []

    class SahteSurec:
        pid = 5001

        def terminate(self):
            gonderilen.append((self.pid, signal.SIGTERM))

    monkeypatch.setattr(audio.os, "kill", lambda pid, sig: gonderilen.append((pid, sig)))
    audio._set_player(SahteSurec())
    try:
        assert audio.stop_playback() is True
    finally:
        audio._player = None

    assert gonderilen == [(5001, signal.SIGCONT), (5001, signal.SIGTERM)]
