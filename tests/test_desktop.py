"""Masaüstü bildirimi testleri.

Hermetiktir: bildirim gösterilmez, `subprocess.run` ve araç araması yamalanır.
"""

import subprocess
from types import SimpleNamespace

import pytest

from pakize import desktop


@pytest.fixture
def platform(monkeypatch):
    def set_platform(name: str, *installed: str):
        monkeypatch.setattr(desktop, "IS_MACOS", name == "macos")
        monkeypatch.setattr(desktop, "IS_WINDOWS", name == "windows")
        monkeypatch.setattr(
            desktop.shutil,
            "which",
            lambda binary: f"/usr/bin/{binary}" if binary in installed else None,
        )

    return set_platform


@pytest.fixture
def run(monkeypatch):
    state = {"commands": [], "returncode": 0, "raises": None}

    def fake_run(command, **kwargs):
        state["commands"].append(command)
        if state["raises"] is not None:
            raise state["raises"]
        return SimpleNamespace(returncode=state["returncode"])

    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    return state


def test_linuxta_notify_send_kullanilir(platform, run):
    platform("linux", "notify-send")

    assert desktop.notify("ffmpeg bulunamadı") is True
    assert run["commands"] == [
        ["/usr/bin/notify-send", "--app-name", "Pakize", "--", "Pakize", "ffmpeg bulunamadı"]
    ]


def test_tire_ile_baslayan_mesaj_secenek_sayilmaz(platform, run):
    platform("linux", "notify-send")

    desktop.notify("-u critical")

    command = run["commands"][0]
    assert command.index("--") < command.index("-u critical")


def test_macosta_metin_betige_gomulmez(platform, run):
    platform("macos", "osascript")

    desktop.notify('tırnak " ve \\ içeren hata')

    command = run["commands"][0]
    assert command[0] == "/usr/bin/osascript"
    assert command[-1] == 'tırnak " ve \\ içeren hata'
    assert not any("tırnak" in part for part in command[:-1])


def test_windowsta_bildirim_gonderilmez(platform, run):
    platform("windows")

    assert desktop.notify("x") is False
    assert run["commands"] == []


def test_arac_yoksa_false(platform, run):
    platform("linux")

    assert desktop.notify("x") is False
    assert run["commands"] == []


@pytest.mark.parametrize(
    "error", [OSError("yok"), subprocess.TimeoutExpired(["notify-send"], 5)]
)
def test_arac_hatasi_disari_sizmaz(platform, run, error):
    platform("linux", "notify-send")
    run["raises"] = error

    assert desktop.notify("x") is False


def test_basarisiz_cikis_false(platform, run):
    platform("linux", "notify-send")
    run["returncode"] = 1

    assert desktop.notify("x") is False
