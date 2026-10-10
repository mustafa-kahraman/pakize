"""Ortak test kurulumu."""

import subprocess

import pytest

from pakize import desktop, i18n


@pytest.fixture(autouse=True)
def turkce_arayuz():
    """Testleri Türkçe arayüze sabitler.

    Testler mesajları Türkçe doğrular; makinenin `LANG`'ine göre dil değişirse
    aynı test bir makinede geçip diğerinde kalırdı. İngilizce davranışı test
    etmek isteyen, fixture'dan sonra `set_language("en")` çağırır.
    """
    i18n.set_language("tr")
    yield
    i18n.set_language(None)


@pytest.fixture(autouse=True)
def gecici_surec_kaydi(tmp_path_factory, monkeypatch):
    """Süreç kaydını geçici dizine taşır.

    Kayıt gerçek oturum dizininde tutulsaydı testler, o sırada gerçekten
    çalan bir Pakize'yi görür ve "kayıt boş" bekleyen testler kalırdı.
    """
    monkeypatch.setenv(
        "XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("runtime"))
    )


class _SessizSubprocess:
    """`pakize.desktop` için `subprocess` yerine geçer; `run` komut çalıştırmaz.

    Diğer her şey (`DEVNULL`, `TimeoutExpired`...) gerçek modülden gelir;
    `tests/test_desktop.py` kendi `run` sahtesini bu nesneye takabilir.
    """

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, command, **kwargs):
        return subprocess.CompletedProcess(command, 0)


@pytest.fixture(autouse=True)
def masaustu_bildirimi_yok(monkeypatch):
    """Hiçbir test gerçek masaüstü bildirimi göstermez.

    Bazı yollar hatayı `desktop.notify` ile bildirir; yamalanmazsa testler
    geliştiricinin masaüstünde gerçekten `notify-send` çalıştırır. Yalnız
    `pakize.desktop` içindeki `subprocess` değiştirilir, global
    `subprocess.run` değil; işçi testleri etkilenmez.
    """
    monkeypatch.setattr(desktop, "subprocess", _SessizSubprocess())
