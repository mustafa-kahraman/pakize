"""Pano kaynağı testleri.

Hermetiktir: gerçek pano aracı çalıştırılmaz, `subprocess.run` yamalanır.
"""

import subprocess
from types import SimpleNamespace

import pytest

from pakize.sources import clipboard
from pakize.sources.clipboard import ClipboardError, read_clipboard


@pytest.fixture(autouse=True)
def linux_varsayimi(monkeypatch):
    """Testler varsayılan olarak Linux'ta koşuyormuş gibi davranır.

    Platforma bağlı davranışı sınayan testler bunu kendisi ezer; böylece
    testin sonucu, koştuğu makineye değil kurduğu senaryoya bağlı kalır.
    """
    monkeypatch.setattr(clipboard, "IS_MACOS", False)
    monkeypatch.setattr(clipboard, "IS_WINDOWS", False)


@pytest.fixture
def kurulu(monkeypatch):
    """Hangi araçların "kurulu" sayılacağını belirleyen yardımcı."""

    def ayarla(*binaries: str, session: str = "x11"):
        monkeypatch.setenv("XDG_SESSION_TYPE", session)
        monkeypatch.setattr(
            clipboard.shutil,
            "which",
            lambda name: f"/usr/bin/{name}" if name in binaries else None,
        )

    return ayarla


@pytest.fixture
def calistirilan(monkeypatch):
    """`subprocess.run` çağrılarını kaydeder ve sahte sonuç döndürür."""
    kayit: list[list[str]] = []
    sonuclar: dict[str, SimpleNamespace] = {}

    def sahte_run(command, **kwargs):
        kayit.append(command)
        varsayilan = SimpleNamespace(returncode=0, stdout="pano içeriği", stderr="")
        return sonuclar.get(command[0], varsayilan)

    monkeypatch.setattr(clipboard.subprocess, "run", sahte_run)
    return SimpleNamespace(kayit=kayit, sonuclar=sonuclar)


def test_pano_icerigi_okunur(kurulu, calistirilan):
    kurulu("xclip")

    assert read_clipboard() == "pano içeriği"
    assert calistirilan.kayit == [["xclip", "-o", "-selection", "clipboard"]]


def test_wayland_oturumunda_wl_paste_tercih_edilir(kurulu, calistirilan):
    kurulu("xclip", "wl-paste", session="wayland")

    read_clipboard()

    assert calistirilan.kayit[0][0] == "wl-paste"


def test_x11_oturumunda_xclip_tercih_edilir(kurulu, calistirilan):
    kurulu("xclip", "wl-paste", session="x11")

    read_clipboard()

    assert calistirilan.kayit[0][0] == "xclip"


def test_macoste_pbpaste_tercih_edilir(kurulu, calistirilan, monkeypatch):
    """XQuartz ile birlikte xclip de kurulu olabilir; doğru cevap pbpaste'te."""
    monkeypatch.setattr(clipboard, "IS_MACOS", True)
    kurulu("xclip", "pbpaste", session="")

    read_clipboard()

    assert calistirilan.kayit == [["pbpaste"]]


def test_windowsta_powershell_ile_okunur(kurulu, calistirilan, monkeypatch):
    monkeypatch.setattr(clipboard, "IS_WINDOWS", True)
    kurulu("powershell", session="")

    read_clipboard()

    komut = calistirilan.kayit[0]
    assert komut[0] == "powershell"
    assert "Get-Clipboard -Raw" in komut[-1]
    # Konsolun kod sayfası Türkçe metni bozar; UTF-8'e sabitlenmeli.
    assert "UTF8" in komut[-1]


def test_pwsh_varsa_eski_powershelle_tercih_edilir(kurulu, calistirilan, monkeypatch):
    monkeypatch.setattr(clipboard, "IS_WINDOWS", True)
    kurulu("pwsh", "powershell", session="")

    read_clipboard()

    assert calistirilan.kayit[0][0] == "pwsh"


def test_hicbir_arac_yoksa_kurulum_ipucu_verilir(kurulu, calistirilan):
    kurulu()

    with pytest.raises(ClipboardError, match="sudo apt install xclip"):
        read_clipboard()


def test_macoste_apt_ipucu_verilmez(kurulu, calistirilan, monkeypatch):
    """Yanlış paket yöneticisini önermek kullanıcıyı çıkmaza yollar."""
    monkeypatch.setattr(clipboard, "IS_MACOS", True)
    kurulu()

    with pytest.raises(ClipboardError, match="pbpaste"):
        read_clipboard()


def test_windowsta_apt_ipucu_verilmez(kurulu, calistirilan, monkeypatch):
    monkeypatch.setattr(clipboard, "IS_WINDOWS", True)
    kurulu()

    with pytest.raises(ClipboardError, match="PowerShell"):
        read_clipboard()


def test_bos_pano_hata_degil_bos_dizgedir(kurulu, calistirilan):
    kurulu("xclip")
    calistirilan.sonuclar["xclip"] = SimpleNamespace(
        returncode=1, stdout="", stderr="Error: target STRING not available"
    )

    assert read_clipboard() == ""


def test_ilk_arac_patlarsa_ikinciye_gecilir(kurulu, calistirilan):
    kurulu("xclip", "xsel")
    calistirilan.sonuclar["xclip"] = SimpleNamespace(
        returncode=1, stdout="", stderr="bağlantı kurulamadı"
    )

    assert read_clipboard() == "pano içeriği"
    assert [command[0] for command in calistirilan.kayit] == ["xclip", "xsel"]


def test_tum_araclar_patlarsa_hata_yukselir(kurulu, calistirilan):
    kurulu("xclip", "xsel")
    for binary in ("xclip", "xsel"):
        calistirilan.sonuclar[binary] = SimpleNamespace(
            returncode=1, stdout="", stderr="ekran yok"
        )

    with pytest.raises(ClipboardError, match="ekran yok"):
        read_clipboard()


def test_zaman_asimi_hataya_cevrilir(kurulu, monkeypatch):
    kurulu("xclip")

    def patla(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=5)

    monkeypatch.setattr(clipboard.subprocess, "run", patla)

    with pytest.raises(ClipboardError, match="yanıt vermedi"):
        read_clipboard()


# --- panoya yazma ------------------------------------------------------------


def test_metin_panoya_yazilir(kurulu, calistirilan):
    from pakize.sources.clipboard import write_clipboard

    kurulu("xclip")

    write_clipboard("dikte metni")

    assert calistirilan.kayit == [["xclip", "-i", "-selection", "clipboard"]]


def test_yazarken_cikti_boruya_baglanmaz(kurulu, monkeypatch):
    """xclip/wl-copy arka planda kalır; boru açık kalsa Pakize sonsuza dek beklerdi."""
    from pakize.sources.clipboard import write_clipboard

    kurulu("wl-copy", session="wayland")
    seen: dict = {}

    def sahte_run(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(clipboard.subprocess, "run", sahte_run)

    write_clipboard("ağırlık")

    assert seen["input"] == "ağırlık".encode()
    assert seen["stdout"] is subprocess.DEVNULL
    assert seen["stderr"] is subprocess.DEVNULL


def test_wayland_oturumunda_wl_copy_tercih_edilir(kurulu, calistirilan):
    from pakize.sources.clipboard import write_clipboard

    kurulu("xclip", "wl-copy", session="wayland")

    write_clipboard("x")

    assert calistirilan.kayit[0][0] == "wl-copy"


def test_yazma_araci_yoksa_kurulum_ipucu(kurulu):
    from pakize.sources.clipboard import write_clipboard

    kurulu()

    with pytest.raises(ClipboardError, match="xclip"):
        write_clipboard("x")


def test_yazma_basarisizsa_cikis_kodu_bildirilir(kurulu, calistirilan):
    from pakize.sources.clipboard import write_clipboard

    kurulu("xsel")
    calistirilan.sonuclar["xsel"] = SimpleNamespace(returncode=1, stdout="", stderr="")

    with pytest.raises(ClipboardError, match="xsel: çıkış kodu 1"):
        write_clipboard("x")
