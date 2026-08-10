"""Süreç kaydı testleri.

Hermetiktir: gerçek süreç öldürülmez, `os.kill` ve `/proc` denetimi yamalanır.
"""

import signal

import pytest

from pakize import runtime


@pytest.fixture(autouse=True)
def gecici_kayit(tmp_path, monkeypatch):
    """Kaydı geçici dizine taşır; gerçek oturum durumuna dokunulmaz."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def pakize_surecleri(monkeypatch):
    """Hangi süreçlerin "yaşayan Pakize" sayılacağını belirler."""

    def ayarla(*pids: int):
        monkeypatch.setattr(runtime, "_is_pakize", lambda pid: pid in pids)

    return ayarla


def test_kayit_yazilir_ve_okunur(pakize_surecleri):
    pakize_surecleri(4242)
    runtime.register(4242)

    assert runtime.running_pid() == 4242


def test_kayit_yoksa_none_doner():
    assert runtime.running_pid() is None
    assert runtime.running_pids() == []


def test_es_zamanli_calmalar_birbirini_ezmez(pakize_surecleri):
    """İkinci çalma birincinin kaydını ezerse birincisi durdurulamaz kalır."""
    pakize_surecleri(1111, 2222)
    runtime.register(1111)
    runtime.register(2222)

    assert sorted(runtime.running_pids()) == [1111, 2222]


def test_bayat_kayit_temizlenir(pakize_surecleri):
    pakize_surecleri()  # hiçbir süreç yaşamıyor
    runtime.register(4242)

    assert runtime.running_pids() == []
    assert not (runtime.state_dir() / "4242").exists()


def test_yasayan_kayitlar_bayatlardan_etkilenmez(pakize_surecleri):
    pakize_surecleri(1111)
    runtime.register(1111)
    runtime.register(2222)

    assert runtime.running_pids() == [1111]


def test_sayi_olmayan_dosyalar_yoksayilir(pakize_surecleri):
    pakize_surecleri(1111)
    runtime.register(1111)
    (runtime.state_dir() / "notlar.txt").write_text("x", encoding="utf-8")

    assert runtime.running_pids() == [1111]


def test_clear_yalnizca_kendi_kaydini_siler(pakize_surecleri):
    pakize_surecleri(1111, 2222)
    runtime.register(1111)
    runtime.register(2222)

    runtime.clear(2222)

    assert runtime.running_pids() == [1111]


def test_stop_sonlandirma_sinyali_gonderir(monkeypatch):
    gonderilen: list[tuple[int, int]] = []
    monkeypatch.setattr(
        runtime.os, "kill", lambda pid, sig: gonderilen.append((pid, sig))
    )

    assert runtime.stop(4242) is True
    assert gonderilen == [(4242, signal.SIGTERM)]


def test_olmus_surec_hata_degil(monkeypatch):
    def patla(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(runtime.os, "kill", patla)
    runtime.register(4242)

    assert runtime.stop(4242) is False
    assert not (runtime.state_dir() / "4242").exists()


def test_izin_yoksa_false_doner(monkeypatch):
    def patla(pid, sig):
        raise PermissionError

    monkeypatch.setattr(runtime.os, "kill", patla)

    assert runtime.stop(4242) is False
