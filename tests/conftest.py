"""Ortak test kurulumu."""

import pytest

from pakize import i18n


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
