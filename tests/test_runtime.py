"""Süreç kaydı testleri.

Hermetiktir: gerçek süreç öldürülmez, `psutil` sahte süreçlerle değiştirilir.
"""

import os
import time

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


# --- okuma sırası -------------------------------------------------------------


@pytest.fixture
def zaman(monkeypatch):
    """`time.time_ns`'i elle ilerletir; sıra zaman damgasından okunur."""
    simdi = {"ns": 1_000}

    def ayarla(ns: int):
        simdi["ns"] = ns

    monkeypatch.setattr(runtime.time, "time_ns", lambda: simdi["ns"])
    return ayarla


def test_sira_kayit_zamanina_gore_kurulur_dosya_zamanina_degil(
    pakize_surecleri, zaman
):
    """mtime dosya sistemine göre kaba olabilir; sıra kayda yazılan damgadan okunur."""
    pakize_surecleri(1111, 2222)
    zaman(200)
    runtime.register(1111)
    zaman(100)
    runtime.register(2222)
    # Dosya zamanları tersini söylesin: 1111 daha eski görünsün.
    os.utime(runtime.state_dir() / "1111", (1, 1))
    os.utime(runtime.state_dir() / "2222", (9_000_000, 9_000_000))

    assert runtime.running_pids() == [2222, 1111]
    assert runtime.running_pid() == 2222


def test_ayni_anda_giren_kayitlarda_kucuk_pid_onde(pakize_surecleri, zaman):
    pakize_surecleri(1111, 2222)
    zaman(500)
    runtime.register(2222)
    runtime.register(1111)

    assert runtime.running_pids() == [1111, 2222]


def test_kayit_metnin_ozetini_tasir_metni_degil(pakize_surecleri):
    pakize_surecleri(1111, 2222)
    runtime.register(1111, text="gizli metin")
    runtime.register(2222)

    birinci, ikinci = runtime.entries()
    assert birinci.text_hash == runtime._text_hash("gizli metin")
    assert ikinci.text_hash is None
    assert "gizli metin" not in (runtime.state_dir() / "1111").read_text(encoding="utf-8")


def test_eski_bicimdeki_kayit_calan_sayilir(pakize_surecleri, zaman):
    """Önceki sürüm dosyaya yalnız pid yazıyordu; yaşıyorsa sıranın başındadır."""
    pakize_surecleri(1111, 2222)
    zaman(50)
    runtime.register(2222)
    (runtime.state_dir() / "1111").write_text("1111", encoding="utf-8")

    assert runtime.running_pids() == [1111, 2222]


def test_sira_gelmeden_beklenir_oncekiler_bitince_doner(pakize_surecleri, zaman, monkeypatch):
    pakize_surecleri(1111, 2222)
    zaman(100)
    runtime.register(1111)
    zaman(200)
    runtime.register(2222)
    uyumalar: list[float] = []

    def sahte_uyku(seconds):
        uyumalar.append(seconds)
        if len(uyumalar) == 3:
            runtime.clear(1111)

    monkeypatch.setattr(runtime.time, "sleep", sahte_uyku)

    runtime.wait_for_turn(2222)

    assert uyumalar == [runtime.QUEUE_POLL_SECONDS] * 3
    assert runtime.QUEUE_POLL_SECONDS <= 0.2


def test_sira_bastaysa_beklenmez(pakize_surecleri, monkeypatch):
    pakize_surecleri(1111)
    runtime.register(1111)
    monkeypatch.setattr(runtime.time, "sleep", lambda seconds: pytest.fail("beklenmemeli"))

    runtime.wait_for_turn(1111)


def test_kendi_kaydi_silinmisse_bekleme_biter(pakize_surecleri, monkeypatch):
    """`stop --all` kaydı düşürmüşse burada takılı kalınmaz."""
    pakize_surecleri(1111)
    runtime.register(1111)
    monkeypatch.setattr(runtime.time, "sleep", lambda seconds: pytest.fail("beklenmemeli"))

    runtime.wait_for_turn(2222)


def test_onde_ayni_metin_varsa_kayit_geri_alinir(pakize_surecleri, zaman):
    pakize_surecleri(1111, 2222)
    zaman(100)
    assert runtime.register(1111, text="aynı") is True
    zaman(200)
    assert runtime.register(2222, text="aynı") is False

    assert runtime.running_pids() == [1111]


def test_farkli_metin_siraya_girer(pakize_surecleri, zaman):
    pakize_surecleri(1111, 2222)
    zaman(100)
    assert runtime.register(1111, text="bir") is True
    zaman(200)
    assert runtime.register(2222, text="iki") is True

    assert runtime.running_pids() == [1111, 2222]


def test_metinsiz_kayitlar_hicbir_seyle_eslesmez(pakize_surecleri, zaman):
    """Kitap, tekrar ve uyarı sesleri metin taşımaz; birbirine tekrar değildir."""
    pakize_surecleri(1111, 2222, 3333)
    zaman(100)
    assert runtime.register(1111) is True
    zaman(200)
    assert runtime.register(2222) is True
    zaman(300)
    assert runtime.register(3333, text="metin") is True

    assert runtime.running_pids() == [1111, 2222, 3333]


@pytest.mark.parametrize(
    ("once", "sonra"), [(1111, 2222), (2222, 1111)], ids=["kucuk-pid-once", "buyuk-pid-once"]
)
def test_ayni_metinde_ilk_kaydolan_kalir_sira_ne_olursa_olsun(
    pakize_surecleri, zaman, once, sonra
):
    """İki basış aynı damgayı alsa da ilk kaydolan kalır; pid eşitlik bozucu
    sırayı etkileyebilir ama tekrar her zaman ikinci girendir."""
    pakize_surecleri(1111, 2222)
    zaman(500)

    assert runtime.register(once, text="aynı") is True
    assert runtime.register(sonra, text="aynı") is False

    assert runtime.running_pids() == [once]


# --- kayıt kilidi -------------------------------------------------------------


def _kayit_kilidi():
    runtime.state_dir().mkdir(parents=True, exist_ok=True)
    return runtime.state_dir() / runtime.REGISTRATION_LOCK_NAME


def _yaslandir(path, seconds: float) -> None:
    """Dosyanın değişiklik zamanını geriye çeker; gerçek bekleme yerine."""
    moment = time.time() - seconds
    os.utime(path, (moment, moment))


def test_damga_kilit_alinmadan_okunmaz(pakize_surecleri, monkeypatch):
    """Damga sırası görünürlük sırasına eşit olsun diye damga kilit altında alınır."""
    pakize_surecleri(1111)
    kilit = _kayit_kilidi()
    kilit.touch()  # başkası tutuyor
    olaylar: list[str] = []

    def sahte_damga():
        olaylar.append("damga")
        return 1_000

    def sahte_uyku(seconds):
        olaylar.append("bekle")
        kilit.unlink()  # sahibi bıraktı

    monkeypatch.setattr(runtime.time, "time_ns", sahte_damga)
    monkeypatch.setattr(runtime.time, "sleep", sahte_uyku)

    assert runtime.register(1111) is True

    assert olaylar == ["bekle", "damga"]
    assert not kilit.exists()  # kayıt bitince kilit bırakılır
    assert runtime.running_pids() == [1111]


def test_kilit_kayit_bitince_birakilir(pakize_surecleri):
    pakize_surecleri(1111)

    runtime.register(1111)

    assert not _kayit_kilidi().exists()


@pytest.mark.parametrize("icerik", ["", "9999"], ids=["bos", "dolu"])
def test_bayat_kilit_icerigine_bakilmadan_kaldirilir(pakize_surecleri, monkeypatch, icerik):
    pakize_surecleri(1111)
    kilit = _kayit_kilidi()
    kilit.write_text(icerik, encoding="utf-8")
    _yaslandir(kilit, runtime.LOCK_STALE_SECONDS + 1)
    monkeypatch.setattr(runtime.time, "sleep", lambda seconds: pytest.fail("beklenmemeli"))

    assert runtime.register(1111) is True

    assert runtime.running_pids() == [1111]
    assert not kilit.exists()


@pytest.mark.parametrize("yas", [0.0, 1.0], ids=["yeni", "bir-saniyelik"])
def test_taze_kilit_beklenir_silinmez(pakize_surecleri, monkeypatch, yas):
    pakize_surecleri(1111)
    kilit = _kayit_kilidi()
    kilit.touch()
    _yaslandir(kilit, yas)
    beklemeler: list[float] = []

    def sahte_uyku(seconds):
        beklemeler.append(seconds)
        assert kilit.exists()  # beklerken dokunulmadı
        kilit.unlink()  # sahibi bıraktı

    monkeypatch.setattr(runtime.time, "sleep", sahte_uyku)

    assert runtime.register(1111) is True

    assert beklemeler == [runtime.LOCK_POLL_SECONDS]
    assert runtime.LOCK_POLL_SECONDS <= 0.01
    assert runtime.LOCK_STALE_SECONDS == 2.0


def test_kilit_birakilamazsa_sonraki_bayatlayinca_gecer(pakize_surecleri, monkeypatch):
    """Windows'ta kilit silinemeyebilir (PermissionError): kayıt çökmez, kilit
    kalır; sonraki giren kilit yaşlanınca kaldırıp geçer."""
    pakize_surecleri(1111, 2222)
    kilit = _kayit_kilidi()
    gercek_unlink = runtime.Path.unlink
    inatci = {"acik": True}

    def inatci_unlink(self, missing_ok=False):
        if inatci["acik"] and self.name == runtime.REGISTRATION_LOCK_NAME:
            raise PermissionError(13, "Permission denied", str(self))
        return gercek_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(runtime.Path, "unlink", inatci_unlink)

    assert runtime.register(1111) is True
    assert kilit.exists()  # bırakılamadı, kaldı

    inatci["acik"] = False
    beklemeler: list[float] = []

    def sahte_uyku(seconds):
        beklemeler.append(seconds)
        _yaslandir(kilit, runtime.LOCK_STALE_SECONDS + 1)  # iki saniye geçti

    monkeypatch.setattr(runtime.time, "sleep", sahte_uyku)

    assert runtime.register(2222) is True

    assert len(beklemeler) == 1
    assert runtime.running_pids() == [1111, 2222]
    assert not kilit.exists()


@pytest.mark.parametrize("nerede", ["time_ns", "_duplicate_registered"], ids=["damgada", "denetimde"])
def test_kayit_sirasinda_kesilirse_kilit_ve_kayit_kalmaz(pakize_surecleri, monkeypatch, nerede):
    """Sinyal kaydın ortasına düşerse ne kilit ne yarım kayıt geride kalır."""
    pakize_surecleri(1111)

    def kes(*args, **kwargs):
        raise KeyboardInterrupt

    hedef = runtime.time if nerede == "time_ns" else runtime
    monkeypatch.setattr(hedef, nerede, kes)

    with pytest.raises(KeyboardInterrupt):
        runtime.register(1111, text="metin")

    assert not _kayit_kilidi().exists()
    assert runtime.running_pids() == []
    assert list(runtime.state_dir().iterdir()) == []


def test_silinemeyen_kayit_hata_degil_ve_canli_sayilmaz(pakize_surecleri, monkeypatch):
    """Windows'ta açık dosya silinemez (PermissionError); kayıt yerinde kalır,
    sahibi ölünce yok sayılır."""
    pakize_surecleri(1111)
    runtime.register(1111)

    def inatci_unlink(self, missing_ok=False):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(runtime.Path, "unlink", inatci_unlink)

    runtime.clear(1111)
    assert (runtime.state_dir() / "1111").exists()

    pakize_surecleri()  # sahibi öldü
    assert runtime.running_pids() == []
    assert runtime.running_pid() is None


def test_dikte_kaydi_calma_kaydindan_ayri_tutulur(pakize_surecleri):
    pakize_surecleri(11, 22)
    runtime.register(11)
    runtime.register(22, runtime.DICTATION_STATE_NAME)

    assert runtime.running_pids() == [11]
    assert runtime.running_pids(runtime.DICTATION_STATE_NAME) == [22]

    runtime.clear(22, runtime.DICTATION_STATE_NAME)

    assert runtime.running_pids(runtime.DICTATION_STATE_NAME) == []
    assert runtime.running_pids() == [11]
