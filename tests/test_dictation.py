"""Dikte testleri.

Hermetiktir: mikrofon açılmaz, ffmpeg çalışmaz, ses çalınmaz; `Popen`, ton
üretimi, deşifre sunucusu ve motor yamalanır. Süreç kaydı geçici dizindedir.
"""

import contextlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pakize import dictation, runtime
from pakize.asr import AsrUnavailable
from pakize.config import Config
from pakize.dictation import DictationError, Recorder, StopRequest
from pakize.sources import ClipboardError


@pytest.fixture(autouse=True)
def gecici_dizinler(tmp_path, monkeypatch):
    """Süreç kaydı ve ton önbelleği geçici dizine gider; beklemeler anlıktır."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(dictation.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runtime, "_is_pakize", lambda pid: True)


@pytest.fixture
def calinanlar(monkeypatch) -> list[Path]:
    kayit: list[Path] = []
    monkeypatch.setattr(dictation.audio, "play", kayit.append)
    return kayit


@pytest.fixture
def uretilen_tonlar(monkeypatch) -> list[Path]:
    """ffmpeg yerine sahte ton dosyası yazar; hangi dosyaların üretildiğini tutar."""
    kayit: list[Path] = []

    def sahte_render(definition, target):
        target.write_bytes(b"RIFF-ton")
        kayit.append(target)

    monkeypatch.setattr(dictation, "_render_tone", sahte_render)
    return kayit


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(dictation, "IS_MACOS", False)
    monkeypatch.setattr(dictation, "IS_WINDOWS", False)


# --- tonlar ------------------------------------------------------------------


def test_varsayilan_ton_ilk_seferde_uretilip_onbellege_yazilir(uretilen_tonlar):
    first = dictation.tone("start", Config())
    second = dictation.tone("start", Config())

    assert first == second
    assert first.parent == dictation.tones_dir()
    assert first.read_bytes() == b"RIFF-ton"
    # Bir kez üretilir; geçici ada yazılıp taşınır, yarım dosya kalmaz.
    assert len(uretilen_tonlar) == 1
    assert sorted(dictation.tones_dir().iterdir()) == [first]


def test_her_tonun_dosyasi_ayridir(uretilen_tonlar):
    paths = {name: dictation.tone(name, Config()) for name in dictation.TONES}

    assert len(set(paths.values())) == len(dictation.TONES)
    for name, path in paths.items():
        assert path.name.startswith(f"{name}-")


def test_config_teki_ses_dosyasi_ton_yerine_gecer(tmp_path, uretilen_tonlar):
    custom = tmp_path / "bip.mp3"
    custom.write_bytes(b"mp3")

    path = dictation.tone("done", replace(Config(), dictate_done_sound=custom))

    assert path == custom
    assert uretilen_tonlar == []


def test_config_teki_ses_dosyasi_yoksa_anlamli_hata(tmp_path):
    missing = tmp_path / "yok.mp3"

    with pytest.raises(DictationError, match="dictate_error_sound"):
        dictation.tone("error", replace(Config(), dictate_error_sound=missing))


def test_ton_argumanlari_her_nota_icin_bir_girdi_kurar():
    arguments = dictation._tone_arguments(dictation.TONES["start"], Path("t.wav"))

    assert arguments.count("lavfi") == 2
    graph = arguments[arguments.index("-filter_complex") + 1]
    assert "concat=n=2" in graph
    assert f"volume={dictation.TONE_VOLUME}" in graph
    assert arguments[-1] == "t.wav"


# --- mikrofon ----------------------------------------------------------------


def test_linux_varsayilani_pulse(linux):
    assert dictation.microphone(Config()) == ("pulse", "default")


def test_macos_varsayilani_avfoundation(monkeypatch):
    monkeypatch.setattr(dictation, "IS_MACOS", True)
    monkeypatch.setattr(dictation, "IS_WINDOWS", False)

    assert dictation.microphone(Config()) == ("avfoundation", ":0")


def test_windows_mikrofon_adi_ister(monkeypatch):
    monkeypatch.setattr(dictation, "IS_MACOS", False)
    monkeypatch.setattr(dictation, "IS_WINDOWS", True)

    with pytest.raises(DictationError, match="dshow"):
        dictation.microphone(Config())


def test_config_teki_mikrofon_varsayilani_ezer(linux):
    config = replace(Config(), dictate_microphone="dshow:audio=Mikrofon (USB)")

    assert dictation.microphone(config) == ("dshow", "audio=Mikrofon (USB)")


@pytest.mark.parametrize("spec", ["default", "pulse:", ":default"])
def test_bicimsiz_mikrofon_ayari_reddedilir(linux, spec):
    with pytest.raises(DictationError, match="biçim:aygıt"):
        dictation.microphone(replace(Config(), dictate_microphone=spec))


# --- kayıt -------------------------------------------------------------------


class SahteFfmpeg:
    """`subprocess.Popen` yerine geçen kayıt süreci."""

    def __init__(self, command, destination_bytes=b"", exit_code=None, log=b""):
        self.command = command
        self.stdin = _Boru()
        self.exit_code = exit_code
        self.signals: list[str] = []
        self.destination = Path(command[-1])
        self.destination_bytes = destination_bytes
        self.log = log
        self._quit_ends = True

    def poll(self):
        return self.exit_code

    @property
    def returncode(self):
        return self.exit_code

    def wait(self, timeout=None):
        if self.exit_code is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.exit_code

    def on_quit(self):
        if self._quit_ends:
            self.destination.write_bytes(self.destination_bytes)
            self.exit_code = 0

    def terminate(self):
        self.signals.append("terminate")
        self.exit_code = -15

    def kill(self):
        self.signals.append("kill")
        self.exit_code = -9


class _Boru:
    def __init__(self):
        self.written = b""
        self.closed = False
        self.owner = None

    def write(self, data):
        self.written += data

    def flush(self):
        if self.owner is not None:
            self.owner.on_quit()

    def close(self):
        self.closed = True


@pytest.fixture
def ffmpeg(monkeypatch):
    """`Popen`'ı yamalar; başlatılan kayıt süreçlerini ve davranışını ayarlatır."""
    state = {"processes": [], "bytes": b"RIFF" + b"\0" * 100, "exit_code": None, "log": b""}

    def fake_popen(command, stdin=None, stdout=None, stderr=None, preexec_fn=None):
        stderr.write(state["log"])
        process = SahteFfmpeg(
            command,
            destination_bytes=state["bytes"],
            exit_code=state["exit_code"],
            log=state["log"],
        )
        process.stdin.owner = process
        if state["exit_code"] is not None:
            # Süreç açılır açılmaz ölmüştür; dosya yazmaz.
            process._quit_ends = False
        state["processes"].append(process)
        return process

    monkeypatch.setattr(dictation.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dictation.audio, "ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    return state


def test_kayit_komutu_mikrofonu_tek_kanal_16khz_ve_sure_sinirli_acar(tmp_path, ffmpeg):
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)

    recorder.start()

    command = ffmpeg["processes"][0].command
    assert command[0] == "/usr/bin/ffmpeg"
    assert command[command.index("-f") + 1] == "pulse"
    assert command[command.index("-i") + 1] == "default"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-t") + 1] == "300"
    assert command[-1] == str(tmp_path / "kayit.wav")


def test_kayit_q_ile_kibarca_bitirilir(tmp_path, ffmpeg):
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)
    recorder.start()

    path = recorder.stop()

    process = ffmpeg["processes"][0]
    assert path == tmp_path / "kayit.wav"
    assert process.stdin.written == b"q"
    assert process.stdin.closed
    assert process.signals == []
    assert not recorder.running()


def test_q_ya_uymayan_ffmpeg_zorla_kapatilir(tmp_path, ffmpeg):
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)
    recorder.start()
    process = ffmpeg["processes"][0]
    process._quit_ends = False
    (tmp_path / "kayit.wav").write_bytes(b"RIFF" + b"\0" * 100)

    recorder.stop()

    assert process.signals == ["terminate"]


def test_bos_kayit_hata_verir(tmp_path, ffmpeg):
    ffmpeg["bytes"] = b"RIFF" + b"\0" * 40
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)
    recorder.start()

    with pytest.raises(DictationError, match="ses gelmedi"):
        recorder.stop()


def test_acilamayan_ffmpeg_gunlugu_ile_bildirilir(tmp_path, ffmpeg):
    ffmpeg["exit_code"] = 1
    ffmpeg["log"] = b"pulse: Connection refused\n"
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)
    recorder.start()

    with pytest.raises(DictationError, match="çıkış kodu 1") as info:
        recorder.stop()

    assert "Connection refused" in str(info.value)


def test_abort_sessizce_keser_ve_tekrar_cagrilabilir(tmp_path, ffmpeg):
    recorder = Recorder(tmp_path / "kayit.wav", "pulse", "default", 300)
    recorder.start()

    recorder.abort()
    recorder.abort()

    assert ffmpeg["processes"][0].signals == ["terminate"]


def test_ffmpeg_yoksa_anlamli_hata(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise OSError("No such file")

    monkeypatch.setattr(dictation.audio, "ffmpeg_binary", lambda: "/yok/ffmpeg")
    monkeypatch.setattr(dictation.subprocess, "Popen", missing)

    with pytest.raises(DictationError, match="Kayıt başlatılamadı"):
        Recorder(tmp_path / "kayit.wav", "pulse", "default", 300).start()


# --- ikinci basış ------------------------------------------------------------


def test_suren_dikte_yoksa_bitirilecek_bir_sey_yoktur():
    assert dictation.request_stop() is StopRequest.NONE


def test_ikinci_basis_bayrak_birakir():
    runtime.register(4242, runtime.DICTATION_STATE_NAME)

    assert dictation.request_stop() is StopRequest.REQUESTED
    assert dictation._stop_flag(4242).exists()


def test_ucuncu_basis_bayragi_zaten_bulur():
    runtime.register(4242, runtime.DICTATION_STATE_NAME)
    dictation.request_stop()

    assert dictation.request_stop() is StopRequest.ALREADY


def test_calan_ses_kaydi_dikte_sayilmaz():
    runtime.register(4242)

    assert dictation.request_stop() is StopRequest.NONE


# --- akış --------------------------------------------------------------------


class SahteMotor:
    def __init__(self, text="merhaba dünya"):
        self.text = text
        self.transcribed: list[Path] = []

    def transcribe(self, audio):
        self.transcribed.append(audio)
        return self.text


class SahteSunucu:
    """`launch_asr_server`'ın tutamacı; hazır olmanın ne zaman beklendiğini kaydeder."""

    def __init__(self, url, events):
        self.url = url
        self.events = events

    def wait_ready(self):
        self.events.append("server-ready")


@pytest.fixture
def desifre(monkeypatch):
    """Sunucu ve motoru yamalar; sunucunun açılış-kapanışını kaydeder."""
    state = {"motor": SahteMotor(), "events": [], "url": "http://127.0.0.1:1"}

    @contextlib.contextmanager
    def fake_server(config):
        state["events"].append("server-up")
        try:
            yield SahteSunucu(state["url"], state["events"])
        finally:
            state["events"].append("server-down")

    monkeypatch.setattr(dictation, "check_asr_setup", lambda config: None)
    monkeypatch.setattr(dictation, "launch_asr_server", fake_server)
    monkeypatch.setattr(
        dictation, "create_asr_engine", lambda name, config: state["motor"]
    )
    return state


@pytest.fixture
def ikinci_basis(monkeypatch):
    """Bekleme döngüsüne girilir girilmez "bitir" bayrağı bırakılmış sayılır."""
    original = dictation._registered

    @contextlib.contextmanager
    def registered_with_flag():
        with original() as stop_requested:
            import os

            dictation._stop_flag(os.getpid()).touch()
            yield stop_requested

    monkeypatch.setattr(dictation, "_registered", registered_with_flag)


def test_dikte_sirasi_ton_kayit_desifre_teslim_ton(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis
):
    delivered: list[str] = []

    text = dictation.dictate(Config(), deliver=delivered.append)

    assert text == "merhaba dünya"
    assert delivered == ["merhaba dünya"]
    assert [path.name.split("-")[0] for path in calinanlar] == ["start", "stop", "done"]
    assert desifre["events"] == ["server-up", "server-ready", "server-down"]
    assert desifre["motor"].transcribed[0].name == "recording.wav"
    assert ffmpeg["processes"][0].stdin.written == b"q"


def test_bitir_istegi_sunucunun_hazir_olmasini_beklemez(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis, monkeypatch
):
    """Kısa konuşmada model hâlâ yükleniyor olabilir; kayıt yine de hemen kapanır."""
    original_stop = Recorder.stop

    def recording_stop(self):
        desifre["events"].append("recording-stopped")
        return original_stop(self)

    monkeypatch.setattr(Recorder, "stop", recording_stop)
    monkeypatch.setattr(
        dictation.audio,
        "play",
        lambda path: desifre["events"].append(path.name.split("-")[0]),
    )

    dictation.dictate(Config(), deliver=lambda text: None)

    assert desifre["events"] == [
        "start", "server-up", "recording-stopped", "stop", "server-ready", "server-down", "done"
    ]


def test_son_kayit_onbellekte_saklanir(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis
):
    dictation.dictate(Config(), deliver=lambda text: None)

    kept = dictation.last_recording_path()
    assert kept.parent == dictation.tones_dir().parent
    assert kept.read_bytes() == ffmpeg["bytes"]


def test_son_kayit_saklanamazsa_dikte_surer(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis, monkeypatch
):
    def broken(source, target):
        raise OSError("disk dolu")

    monkeypatch.setattr(dictation.shutil, "copyfile", broken)

    assert dictation.dictate(Config(), deliver=lambda text: None) == "merhaba dünya"


def test_baslangic_tonu_kayittan_once_calinir(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis, monkeypatch
):
    order: list[str] = []
    original_start = Recorder.start
    monkeypatch.setattr(dictation.audio, "play", lambda path: order.append(path.name.split("-")[0]))
    monkeypatch.setattr(
        Recorder, "start", lambda self: (order.append("record"), original_start(self))
    )

    dictation.dictate(Config(), deliver=lambda text: None)

    assert order[:2] == ["start", "record"]


def test_motor_dis_sunucu_adresiyle_kurulur(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis, monkeypatch
):
    seen: list[str] = []
    monkeypatch.setattr(
        dictation,
        "create_asr_engine",
        lambda name, config: (seen.append(config.asr_server_url), desifre["motor"])[1],
    )

    dictation.dictate(Config(), deliver=lambda text: None)

    assert seen == ["http://127.0.0.1:1"]


def test_surec_kaydi_dikte_bitince_temizlenir(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis
):
    dictation.dictate(Config(), deliver=lambda text: None)

    assert runtime.running_pids(runtime.DICTATION_STATE_NAME) == []
    assert dictation.request_stop() is StopRequest.NONE


def test_sure_dolunca_kayit_kendiliginden_biter(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar
):
    """İkinci basış hiç gelmezse ffmpeg `-t` ile kapanır; akış devam eder."""
    polls = {"count": 0}
    original_running = Recorder.running

    def running_then_done(self):
        polls["count"] += 1
        if polls["count"] >= 3:
            ffmpeg["processes"][0].on_quit()
        return original_running(self)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Recorder, "running", running_then_done)
        text = dictation.dictate(Config(), deliver=lambda t: None)

    assert text == "merhaba dünya"
    assert polls["count"] >= 3


def test_terminalde_ctrl_c_kaydi_bitirir(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, monkeypatch
):
    def interrupted(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(Recorder, "running", interrupted)

    text = dictation.dictate(Config(), deliver=lambda t: None)

    assert text == "merhaba dünya"


def test_bos_desifre_hata_sayilir(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis
):
    desifre["motor"].text = ""
    delivered: list[str] = []

    with pytest.raises(DictationError, match="konuşma bulunamadı"):
        dictation.dictate(Config(), deliver=delivered.append)

    assert delivered == []
    assert [path.name.split("-")[0] for path in calinanlar] == ["start", "stop"]


def test_teslim_basarisizsa_hazir_tonu_calinmaz(
    linux, ffmpeg, desifre, calinanlar, uretilen_tonlar, ikinci_basis
):
    def broken(text):
        raise ClipboardError("xclip yok")

    with pytest.raises(ClipboardError):
        dictation.dictate(Config(), deliver=broken)

    assert [path.name.split("-")[0] for path in calinanlar] == ["start", "stop"]
    assert runtime.running_pids(runtime.DICTATION_STATE_NAME) == []


def test_eksik_asr_ayari_kayittan_once_yakalanir(
    linux, ffmpeg, calinanlar, uretilen_tonlar, monkeypatch
):
    def missing(config):
        raise AsrUnavailable("asr_model yok")

    monkeypatch.setattr(dictation, "check_asr_setup", missing)

    with pytest.raises(AsrUnavailable):
        dictation.dictate(Config(), deliver=lambda t: None)

    assert calinanlar == []
    assert ffmpeg["processes"] == []


def test_sunucu_acilamazsa_kayit_kesilir(
    linux, ffmpeg, calinanlar, uretilen_tonlar, monkeypatch
):
    @contextlib.contextmanager
    def failing_server(config):
        raise AsrUnavailable("sunucu açılmadı")
        yield

    monkeypatch.setattr(dictation, "check_asr_setup", lambda config: None)
    monkeypatch.setattr(dictation, "launch_asr_server", failing_server)

    with pytest.raises(AsrUnavailable):
        dictation.dictate(Config(), deliver=lambda t: None)

    assert ffmpeg["processes"][0].signals == ["terminate"]
    assert runtime.running_pids(runtime.DICTATION_STATE_NAME) == []


# --- hata anonsu -------------------------------------------------------------


def test_hata_anonsu_once_ton_sonra_mesaj_okur(calinanlar, uretilen_tonlar, monkeypatch):
    notice = Path("dikte-hata.mp3")
    spoken: list[str] = []
    monkeypatch.setattr(
        dictation.notices,
        "dictation_notice",
        lambda message, config: (spoken.append(message), notice)[1],
    )

    dictation.announce_error(Config(), "Kayıt boş: mikrofondan ses gelmedi.\nayrıntı")

    assert calinanlar[0].name.startswith("error-")
    assert calinanlar[1] == notice
    assert spoken == ["Kayıt boş: mikrofondan ses gelmedi."]


def test_hata_anonsu_uretilemezse_sessiz_kalir(calinanlar, uretilen_tonlar, monkeypatch):
    from pakize.engines import EngineError

    def broken(message, config):
        raise EngineError("edge-tts yok")

    monkeypatch.setattr(dictation.notices, "dictation_notice", broken)

    dictation.announce_error(Config(), "bir şey oldu")

    assert len(calinanlar) == 1


def test_hata_anonsu_sesin_dilinde_okunur(calinanlar, uretilen_tonlar, monkeypatch):
    from pakize import i18n

    spoken: list[str] = []
    monkeypatch.setattr(
        dictation.notices,
        "dictation_notice",
        lambda message, config: (spoken.append(message), Path("n.mp3"))[1],
    )
    i18n.set_language("en")

    dictation.announce_error(
        replace(Config(), voice="tr-TR-EmelNeural"), "No speech found in the recording."
    )
    dictation.announce_error(
        replace(Config(), voice="en-US-JennyNeural"), "No speech found in the recording."
    )

    assert spoken == ["Kayıtta konuşma bulunamadı.", "No speech found in the recording."]


def test_sesli_uyari_calinamazsa_bildirim_gosterilir(uretilen_tonlar, monkeypatch):
    """ffplay yoksa ne ton ne okuma duyulur; hata ekrana bildirim olarak gelir."""

    def no_player(path):
        raise dictation.audio.AudioError("ffplay bulunamadı")

    notified: list[str] = []
    monkeypatch.setattr(dictation.audio, "play", no_player)
    monkeypatch.setattr(dictation.notices, "dictation_notice", lambda m, c: Path("n.mp3"))
    monkeypatch.setattr(dictation.desktop, "notify", notified.append)

    dictation.announce_error(Config(), "ffmpeg bulunamadı. Kurmak için: sudo apt install ffmpeg")

    assert notified == ["ffmpeg bulunamadı. Kurmak için: sudo apt install ffmpeg"]


def test_sesli_uyari_calinca_bildirim_gosterilmez(calinanlar, uretilen_tonlar, monkeypatch):
    notified: list[str] = []
    monkeypatch.setattr(dictation.notices, "dictation_notice", lambda m, c: Path("n.mp3"))
    monkeypatch.setattr(dictation.desktop, "notify", notified.append)

    dictation.announce_error(Config(), "bir şey oldu")

    assert notified == []
