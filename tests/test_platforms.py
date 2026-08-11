"""Platforma bağlı kararların testleri.

Hermetiktir: `sys.platform` okunmaz, platform bayrakları yamalanır. Böylece
Windows ve macOS yolları da Linux'ta koşan bir testle doğrulanabilir.
"""

from pathlib import Path

import pytest

from pakize import config as config_modulu
from pakize import platforms


@pytest.fixture
def platform(monkeypatch):
    """Hangi platformda çalışıyormuş gibi davranılacağını belirler."""

    def ayarla(ad: str):
        monkeypatch.setattr(platforms, "IS_WINDOWS", ad == "windows")
        monkeypatch.setattr(platforms, "IS_MACOS", ad == "macos")

    return ayarla


def test_xdg_her_platformda_onceliklidir(platform, monkeypatch, tmp_path):
    platform("windows")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")

    assert platforms.config_home() == tmp_path


def test_windowsta_appdata_kullanilir(platform, monkeypatch):
    platform("windows")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")

    assert platforms.config_home() == Path(r"C:\Users\test\AppData\Roaming")


def test_macoste_nokta_config_kullanilir(platform, monkeypatch):
    """Elle düzenlenen TOML, terminal araçlarının alışılmış yerinde durmalı."""
    platform("macos")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert platforms.config_home() == Path.home() / ".config"


def test_linuxta_nokta_config_kullanilir(platform, monkeypatch):
    platform("linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert platforms.config_home() == Path.home() / ".config"


def test_appdata_yoksa_nokta_confige_dusulur(platform, monkeypatch):
    """Kısıtlı bir Windows ortamında ayarsız kalmaktansa ev dizinine yazarız."""
    platform("windows")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    assert platforms.config_home() == Path.home() / ".config"


@pytest.mark.parametrize(
    ("ad", "beklenen"),
    [
        ("linux", "sudo apt install ffmpeg"),
        ("macos", "brew install ffmpeg"),
        ("windows", "winget install Gyan.FFmpeg"),
    ],
)
def test_kurulum_ipucu_platforma_gore_secilir(platform, ad, beklenen):
    """Yanlış paket yöneticisini önermek kullanıcıyı çıkmaz bir aramaya yollar."""
    platform(ad)

    assert platforms.install_hint("ffmpeg") == beklenen


def test_calibre_ipucu_da_platforma_gore_secilir(platform):
    platform("macos")

    assert platforms.install_hint("calibre") == "brew install --cask calibre"


def test_windows_yolu_gecerli_toml_uretir():
    """Ters bölü TOML'da kaçış başlatır; kaçırılmazsa dosya okunamaz olurdu."""
    windows_yolu = "C:\\Temp\\pakize"
    satir = f"output_dir = {config_modulu._toml_value(Path(windows_yolu))}"

    okunan = config_modulu.tomllib.loads(satir)

    assert okunan["output_dir"] == windows_yolu
