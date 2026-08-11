"""Duraklatma/sürdürme testleri.

Hermetiktir: gerçek süreç ağacına dokunulmaz, `psutil` sahte süreçlerle
değiştirilir. Böylece testler Linux, macOS ve Windows'ta aynı şekilde koşar.
"""

import psutil
import pytest
from typer.testing import CliRunner

from pakize import cli, runtime

runner = CliRunner()

SPEAK_PID = 4242


class SahteOynatici:
    """`psutil.Process`'in kullandığımız kadarını taklit eden sahte ffplay."""

    def __init__(self, pid: int, durum: str, kayit: list[tuple[int, str]]):
        self.pid = pid
        self._durum = durum
        self._kayit = kayit

    def status(self) -> str:
        return self._durum

    def suspend(self) -> None:
        self._kayit.append((self.pid, "suspend"))
        self._durum = psutil.STATUS_STOPPED

    def resume(self) -> None:
        self._kayit.append((self.pid, "resume"))
        self._durum = psutil.STATUS_RUNNING

    def terminate(self) -> None:
        self._kayit.append((self.pid, "terminate"))


@pytest.fixture
def surecler(monkeypatch):
    """Sahte bir süreç ağacı kurar ve uygulanan eylemleri kaydeder."""
    yapilan: list[tuple[int, str]] = []

    def ayarla(**player_states: str):
        oynaticilar = [
            SahteOynatici(int(pid), durum, yapilan)
            for pid, durum in player_states.items()
        ]
        monkeypatch.setattr(
            runtime, "_players", lambda pid: oynaticilar if pid == SPEAK_PID else []
        )

    ayarla()
    return type("Kurulum", (), {"ayarla": staticmethod(ayarla), "yapilan": yapilan})


def test_calan_surec_duraklatilir(surecler):
    surecler.ayarla(**{"5001": psutil.STATUS_RUNNING})

    assert runtime.pause(SPEAK_PID) is True
    assert surecler.yapilan == [(5001, "suspend")]


def test_duraklatilmis_surec_surdurulur(surecler):
    surecler.ayarla(**{"5001": psutil.STATUS_STOPPED})

    assert runtime.resume(SPEAK_PID) is True
    assert surecler.yapilan == [(5001, "resume")]


def test_calan_yoksa_duraklatma_false_doner(surecler):
    surecler.ayarla()

    assert runtime.pause(SPEAK_PID) is False
    assert surecler.yapilan == []


def test_duraklatilmislik_durumdan_okunur(surecler):
    surecler.ayarla(**{"5001": psutil.STATUS_STOPPED})
    assert runtime.is_paused(SPEAK_PID) is True

    surecler.ayarla(**{"5001": psutil.STATUS_RUNNING})
    assert runtime.is_paused(SPEAK_PID) is False


def test_calan_yokken_duraklatilmis_sayilmaz(surecler):
    surecler.ayarla()

    assert runtime.is_paused(SPEAK_PID) is False


def test_olmus_oynatici_duraklatmayi_bozmaz(surecler, monkeypatch):
    """Süreç iki okuma arasında ölebilir; bu hata değil, olağan bir yarıştır."""

    class OlmusOynatici(SahteOynatici):
        def suspend(self):
            raise psutil.NoSuchProcess(self.pid)

    olu = OlmusOynatici(5001, psutil.STATUS_RUNNING, surecler.yapilan)
    monkeypatch.setattr(runtime, "_players", lambda pid: [olu])

    assert runtime.pause(SPEAK_PID) is False


@pytest.mark.parametrize(
    ("ad", "beklenen"),
    [
        ("ffplay", True),
        ("ffplay.exe", True),
        ("FFPLAY.EXE", True),
        ("ffmpeg", False),
        ("ffplayer", False),
    ],
)
def test_oynatici_adi_uzantidan_bagimsiz_taninir(ad, beklenen):
    """Windows'ta aynı süreç `ffplay.exe` adıyla görünür."""

    class AdliSurec:
        def name(self):
            return ad

    assert runtime._is_player(AdliSurec()) is beklenen


def test_duraklat_komutu_calani_duraklatir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [SPEAK_PID])
    monkeypatch.setattr(cli.runtime, "is_paused", lambda pid: False)
    monkeypatch.setattr(cli.runtime, "pause", lambda pid: True)

    sonuc = runner.invoke(cli.app, ["pause"])

    assert sonuc.exit_code == 0
    assert "Duraklatıldı." in sonuc.stdout


def test_duraklat_komutu_duraklatilmisi_surdurur(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [SPEAK_PID])
    monkeypatch.setattr(cli.runtime, "is_paused", lambda pid: True)
    monkeypatch.setattr(cli.runtime, "resume", lambda pid: True)

    sonuc = runner.invoke(cli.app, ["pause"])

    assert sonuc.exit_code == 0
    assert "Devam ediyor." in sonuc.stdout


def test_duraklat_calan_yoksa_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [])

    sonuc = runner.invoke(cli.app, ["pause"])

    assert sonuc.exit_code == 1
    assert "Çalan bir seslendirme yok." in sonuc.stdout


def test_durdurma_once_devam_ettirip_sonra_sonlandirir(monkeypatch):
    """Sıra kritik: devam ettirme sonlandırmadan ÖNCE gelmeli.

    Ters sırada ffplay bekleyen sonlandırma isteğini yutup çalmayı sürdürüyor;
    gerçek süreçlerle doğrulandı.
    """
    from pakize import audio

    yapilan: list[tuple[int, str]] = []

    class SahteSurec:
        pid = 5001

        def terminate(self):
            yapilan.append((self.pid, "terminate"))

    monkeypatch.setattr(
        audio.psutil, "Process", lambda pid: SahteOynatici(pid, "running", yapilan)
    )
    audio._set_player(SahteSurec())
    try:
        assert audio.stop_playback() is True
    finally:
        audio._player = None
        audio._stopped = False

    assert yapilan == [(5001, "resume"), (5001, "terminate")]
