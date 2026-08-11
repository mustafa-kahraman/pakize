"""Süreç kaydı testleri.

Hermetiktir: gerçek süreç öldürülmez, `psutil` sahte süreçlerle değiştirilir.
"""

import psutil
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


class SahteSurec:
    """`psutil.Process`'in kullandığımız kadarını taklit eder."""

    def __init__(self, pid: int, kayit: list[tuple[int, str]]):
        self.pid = pid
        self._kayit = kayit

    def resume(self) -> None:
        self._kayit.append((self.pid, "resume"))

    def terminate(self) -> None:
        self._kayit.append((self.pid, "terminate"))


@pytest.fixture
def surec_agaci(monkeypatch):
    """Ana süreci ve çalma alt süreçlerini sahteler; eylemleri sırayla kaydeder."""
    yapilan: list[tuple[int, str]] = []

    def ayarla(*player_pids: int):
        oynaticilar = [SahteSurec(pid, yapilan) for pid in player_pids]
        monkeypatch.setattr(runtime, "_players", lambda pid: list(oynaticilar))
        monkeypatch.setattr(
            runtime.psutil, "Process", lambda pid: SahteSurec(pid, yapilan)
        )

    ayarla()
    return type("Kurulum", (), {"ayarla": staticmethod(ayarla), "yapilan": yapilan})


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


def test_stop_sureci_sonlandirir(surec_agaci):
    surec_agaci.ayarla()

    assert runtime.stop(4242) is True
    assert surec_agaci.yapilan == [(4242, "terminate")]


def test_stop_once_calani_keser_sonra_sureci(surec_agaci):
    """Sıra kritik ve platforma bağlı.

    Windows'ta süreç sonlandırma sinyal işleyicisini çalıştırmaz: ana süreç
    kendi ffplay'ini kesemeden ölür ve ses öksüz kalıp çalmayı sürdürürdü.
    Bu yüzden çalan ses her platformda önce susturulur.
    """
    surec_agaci.ayarla(5001)

    assert runtime.stop(4242) is True
    assert surec_agaci.yapilan == [
        (5001, "resume"),
        (5001, "terminate"),
        (4242, "terminate"),
    ]


def test_olmus_surec_hata_degil(monkeypatch):
    def patla(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(runtime, "_players", lambda pid: [])
    monkeypatch.setattr(runtime.psutil, "Process", patla)
    runtime.register(4242)

    assert runtime.stop(4242) is False
    assert not (runtime.state_dir() / "4242").exists()


def test_izin_yoksa_false_doner(monkeypatch):
    def patla(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(runtime, "_players", lambda pid: [])
    monkeypatch.setattr(runtime.psutil, "Process", patla)

    assert runtime.stop(4242) is False


def test_devam_ettirme_patlasa_da_sonlandirma_denenir(monkeypatch):
    """Hata yutma tek tek eylemlerin çevresinde olmalı.

    Ortak bir `try` bloğunda `resume` patladığında `terminate` hiç denenmez ve
    ses çalmaya devam ederdi.
    """
    yapilan: list[tuple[int, str]] = []

    class InatciOynatici(SahteSurec):
        def resume(self):
            raise psutil.AccessDenied(self.pid)

    monkeypatch.setattr(
        runtime, "_players", lambda pid: [InatciOynatici(5001, yapilan)]
    )
    monkeypatch.setattr(runtime.psutil, "Process", lambda pid: SahteSurec(pid, yapilan))

    runtime.stop(4242)

    assert yapilan == [(5001, "terminate"), (4242, "terminate")]


def test_ulasilamayan_surec_agaci_bos_liste_doner(monkeypatch):
    """Süreç okunamıyorsa (ölmüş ya da izin yok) çalan yok sayılır."""

    def patla(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(runtime.psutil, "Process", patla)

    assert runtime._players(4242) == []
    assert runtime._is_pakize(4242) is False
