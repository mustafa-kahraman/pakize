"""Deşifre sunucusunun ömrü testleri.

Hermetiktir: gerçek süreç başlatılmaz, `Popen` ve hazırlık yoklaması yamalanır.
"""

import signal
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pakize import platforms
from pakize.asr import AsrError, AsrUnavailable, asr_server
from pakize.asr import server as server_module
from pakize.config import Config


class FakeProcess:
    """`subprocess.Popen` yerine geçer; kapatılma biçimini kaydeder."""

    def __init__(self, command, stdout=None, exit_code=None, ignores_terminate=False):
        self.command = command
        self.stdout = stdout
        self.exit_code = exit_code
        self.ignores_terminate = ignores_terminate
        self.signals: list[str] = []

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.signals.append("terminate")
        if not self.ignores_terminate:
            self.exit_code = -15

    def kill(self):
        self.signals.append("kill")
        self.exit_code = -9

    def wait(self, timeout=None):
        if self.exit_code is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.exit_code


@pytest.fixture
def model_files(tmp_path) -> Config:
    model = tmp_path / "model.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    binary = tmp_path / "llama-server"
    for path in (model, mmproj, binary):
        path.write_bytes(b"x")
    return replace(
        Config(), asr_model=model, asr_mmproj=mmproj, asr_server_binary=binary
    )


@pytest.fixture
def launcher(monkeypatch):
    """`Popen`'ı yamalar; başlatılan süreçleri ve davranışlarını ayarlatır."""
    state = {
        "processes": [],
        "ready": True,
        "exit_code": None,
        "log": b"",
        "ignores_terminate": False,
    }

    def fake_popen(command, stdin=None, stdout=None, stderr=None, preexec_fn=None):
        stdout.write(state["log"])
        process = FakeProcess(
            command,
            stdout=stdout,
            exit_code=state["exit_code"],
            ignores_terminate=state["ignores_terminate"],
        )
        state["processes"].append(process)
        return process

    monkeypatch.setattr(server_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(server_module, "_responds", lambda url: state["ready"])
    monkeypatch.setattr(server_module, "_free_port", lambda: 43210)
    monkeypatch.setattr(server_module.time, "sleep", lambda seconds: None)
    return state


def test_dis_sunucu_adresi_oldugu_gibi_kullanilir(launcher):
    config = replace(Config(), asr_server_url="http://127.0.0.1:8099")

    with asr_server(config) as url:
        assert url == "http://127.0.0.1:8099"

    assert launcher["processes"] == []


def test_ne_adres_ne_model_varsa_kullanilamaz(launcher):
    with pytest.raises(AsrUnavailable, match="asr_model"):
        with asr_server(Config()):
            pass


def test_sunucu_yerelde_bos_portta_ve_cevrimdisi_baslar(model_files, launcher):
    with asr_server(model_files) as url:
        assert url == "http://127.0.0.1:43210"

    command = launcher["processes"][0].command
    assert command[0] == str(model_files.asr_server_binary)
    assert command[command.index("--model") + 1] == str(model_files.asr_model)
    assert command[command.index("--mmproj") + 1] == str(model_files.asr_mmproj)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "43210"
    assert "--offline" in command


def test_is_bitince_sunucu_kapanir(model_files, launcher):
    with asr_server(model_files):
        process = launcher["processes"][0]
        assert process.signals == []

    assert process.signals == ["terminate"]


def test_is_hatayla_bitse_de_sunucu_kapanir(model_files, launcher):
    with pytest.raises(AsrError):
        with asr_server(model_files):
            raise AsrError("deşifre patladı")

    assert launcher["processes"][0].signals == ["terminate"]


def test_kesintide_de_sunucu_kapanir(model_files, launcher):
    with pytest.raises(KeyboardInterrupt):
        with asr_server(model_files):
            raise KeyboardInterrupt

    assert launcher["processes"][0].signals == ["terminate"]


def test_sonlandirma_sinyalinde_de_sunucu_kapanir(model_files, launcher):
    """Python SIGTERM'de `finally` çalıştırmaz; blok bunu çıkışa çevirmeli."""
    with pytest.raises(SystemExit):
        with asr_server(model_files):
            handler = signal.getsignal(signal.SIGTERM)
            handler(signal.SIGTERM, None)

    assert launcher["processes"][0].signals == ["terminate"]


def test_blok_bitince_onceki_sinyal_isleyicisi_geri_konur(model_files, launcher):
    before = signal.getsignal(signal.SIGTERM)

    with asr_server(model_files):
        assert signal.getsignal(signal.SIGTERM) is not before

    assert signal.getsignal(signal.SIGTERM) is before


def test_kibar_kapanmayan_sunucu_zorla_kapatilir(model_files, launcher):
    launcher["ignores_terminate"] = True

    with asr_server(model_files):
        pass

    assert launcher["processes"][0].signals == ["terminate", "kill"]


def test_acilirken_kapanan_sunucu_gunlugu_ile_hata_verir(model_files, launcher):
    launcher["exit_code"] = 1
    launcher["log"] = b"loading model\nerror: failed to load mmproj\n"

    with pytest.raises(AsrError, match="failed to load mmproj") as error:
        with asr_server(model_files):
            pass

    assert "çıkış kodu 1" in str(error.value)


def test_hazir_olmayan_sunucu_sure_dolunca_kapatilir(model_files, launcher, monkeypatch):
    launcher["ready"] = False
    clock = iter([0.0, 0.0, server_module.READY_TIMEOUT + 1])
    monkeypatch.setattr(server_module.time, "monotonic", lambda: next(clock))

    with pytest.raises(AsrError, match="hazır olmadı"):
        with asr_server(model_files):
            pass

    assert launcher["processes"][0].signals == ["terminate"]


def test_model_dosyasi_yoksa_kullanilamaz(model_files, launcher, tmp_path):
    config = replace(model_files, asr_model=tmp_path / "yok.gguf")

    with pytest.raises(AsrUnavailable, match="asr_model"):
        with asr_server(config):
            pass

    assert launcher["processes"] == []


def test_ses_kodlayicisi_olmadan_kullanilamaz(model_files, launcher):
    with pytest.raises(AsrUnavailable, match="asr_mmproj"):
        with asr_server(replace(model_files, asr_mmproj=None)):
            pass


def test_sunucu_programi_bulunamazsa_kurulum_ipucu_verir(
    model_files, launcher, monkeypatch
):
    monkeypatch.setattr(server_module.shutil, "which", lambda name: None)

    with pytest.raises(AsrUnavailable, match="llama.cpp"):
        with asr_server(replace(model_files, asr_server_binary=None)):
            pass


def test_sunucu_programi_path_uzerinden_bulunur(model_files, launcher, monkeypatch):
    monkeypatch.setattr(
        server_module.shutil, "which", lambda name: "/opt/bin/llama-server"
    )

    with asr_server(replace(model_files, asr_server_binary=None)):
        pass

    assert launcher["processes"][0].command[0] == "/opt/bin/llama-server"


def test_program_calistirilamazsa_anlasilir_hata_verir(model_files, monkeypatch):
    def failing_popen(*args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(server_module.subprocess, "Popen", failing_popen)
    monkeypatch.setattr(server_module, "_free_port", lambda: 43210)

    with pytest.raises(AsrError, match="başlatılamadı"):
        with asr_server(model_files):
            pass


def test_linux_disinda_ust_surec_guvencesi_yok(monkeypatch):
    monkeypatch.setattr(platforms.sys, "platform", "darwin")

    assert platforms.die_with_parent() is None


def test_config_model_yollarini_okur(tmp_path):
    from pakize.config import load_config

    path = tmp_path / "config.toml"
    path.write_text(
        'asr_model = "~/m.gguf"\nasr_mmproj = "/a/mm.gguf"\n', encoding="utf-8"
    )

    config = load_config(path)

    assert config.asr_model == Path("~/m.gguf").expanduser()
    assert config.asr_mmproj == Path("/a/mm.gguf")


# --- başlatmadan doğrulama ---------------------------------------------------


def test_ayar_dogrulamasi_surec_baslatmaz(model_files, launcher):
    from pakize.asr import check_asr_setup

    check_asr_setup(model_files)

    assert launcher["processes"] == []


def test_ayar_dogrulamasi_dis_sunucuya_dokunmaz(launcher):
    from pakize.asr import check_asr_setup

    check_asr_setup(replace(Config(), asr_server_url="http://127.0.0.1:8099"))


def test_ayar_dogrulamasi_eksik_modeli_soyler():
    from pakize.asr import check_asr_setup

    with pytest.raises(AsrUnavailable, match="asr_model"):
        check_asr_setup(Config())


def test_ayar_dogrulamasi_eksik_kodlayiciyi_soyler(model_files):
    from pakize.asr import check_asr_setup

    with pytest.raises(AsrUnavailable, match="asr_mmproj"):
        check_asr_setup(replace(model_files, asr_mmproj=None))


def test_ayar_dogrulamasi_olmayan_dosyayi_soyler(model_files, tmp_path):
    from pakize.asr import check_asr_setup

    with pytest.raises(AsrUnavailable, match="asr_server_binary"):
        check_asr_setup(replace(model_files, asr_server_binary=tmp_path / "yok"))


# --- başlat ve hazır-ol ayrı -------------------------------------------------


def test_launch_hazir_olmayi_beklemez(model_files, launcher, monkeypatch):
    from pakize.asr import launch_asr_server

    launcher["ready"] = False
    polls: list[str] = []
    monkeypatch.setattr(server_module, "_responds", lambda url: polls.append(url) or False)

    with launch_asr_server(model_files) as server:
        assert server.url == "http://127.0.0.1:43210"
        assert polls == []
        assert launcher["processes"][0].signals == []

    assert launcher["processes"][0].signals == ["terminate"]


def test_wait_ready_hazir_olunca_doner(model_files, launcher):
    from pakize.asr import launch_asr_server

    with launch_asr_server(model_files) as server:
        server.wait_ready()
        server.wait_ready()

        assert launcher["processes"][0].signals == []


def test_wait_ready_sunucu_cokmusse_hata_verir_ve_kapatir(model_files, launcher):
    from pakize.asr import launch_asr_server

    with launch_asr_server(model_files) as server:
        launcher["processes"][0].exit_code = 3
        launcher["processes"][0].stdout.write(b"model yuklenemedi\n")

        with pytest.raises(AsrError, match="çıkış kodu 3"):
            server.wait_ready()


def test_dis_sunucu_tutamaci_beklemez(launcher):
    from pakize.asr import launch_asr_server

    with launch_asr_server(replace(Config(), asr_server_url="http://127.0.0.1:8099")) as server:
        server.wait_ready()
        assert server.url == "http://127.0.0.1:8099"

    assert launcher["processes"] == []
