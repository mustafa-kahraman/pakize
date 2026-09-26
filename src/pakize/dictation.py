"""Dikte: konuşmayı kaydeder ve metne çevirir.

Akış tek bir klavye kısayoluna bağlıdır ve iki basışla yürür:

1. basış → başlangıç tonu → kayıt başlar → deşifre sunucusu arkada ısınır
2. basış → kayıt biter → bitiş tonu → deşifre → metin teslim → hazır tonu

Tonun sırası kasıtlı: başta tondan **sonra** kayıt açılır, bitişte kayıt
kapandıktan **sonra** ton çalınır; aksi hâlde mikrofon tonun kendisini
kaydeder.

İki basış iki ayrı süreçtir. İlki dikteyi baştan sona yürütür: mikrofon,
sunucu, süre sınırı ve temizlik onun elindedir; böylece `asr.server`'ın
kapanış güvenceleri (SIGTERM, `kill -9`) doğrudan işler. İkincisi yalnızca
"bitir" der: kayıt dizinine bir bayrak dosyası bırakıp çıkar. Sinyal yerine
dosya seçildi; Windows'ta süreçler arası sinyal yok, dosya her yerde var.

Tasarım şartı: sürekli dinleyen ya da ayakta duran hiçbir şey olmayacak.
Mikrofon ve sunucu tek bir diktenin ömrü kadar yaşar; ikinci basış unutulursa
`dictate_max_seconds` kaydı kendiliğinden keser.
"""

from __future__ import annotations

import contextlib
import enum
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import IO, Callable, Iterator

from . import audio, notices, runtime
from .asr import check_asr_setup, create_asr_engine, launch_asr_server
from .config import Config
from .engines import EngineError
from .i18n import _, in_language, voice_language
from .platforms import IS_MACOS, IS_WINDOWS, cache_home, die_with_parent

SAMPLE_RATE = 16000
"""Kayıt örnekleme hızı (Hz). Model bu hızda dinler; fazlası dosyayı büyütür."""

POLL_SECONDS = 0.1
"""İkinci basışın bayrağına bakma aralığı; kayıt en çok bu kadar geç kapanır."""

STOP_GRACE_SECONDS = 5.0
"""ffmpeg'in dosyayı kapatması için tanınan süre; sonra zorla kapatılır."""

LOG_TAIL_LINES = 5
"""Kayıt başarısız olursa hata mesajına eklenecek ffmpeg günlüğü satırı sayısı."""

STOP_FLAG_SUFFIX = ".stop"
"""İkinci basışın bıraktığı bayrak: kayıt dizininde `<pid>.stop`."""

WAV_HEADER_BYTES = 44
"""Boş bir WAV dosyasının boyutu; bundan büyük değilse ses gelmemiştir."""

TONE_VOLUME = 0.3
"""Üretilen tonların ses düzeyi; tam ölçek kulak tırmalar."""


class DictationError(RuntimeError):
    """Dikte sırasında oluşan, kullanıcıya gösterilebilir hata."""


# --- tonlar ------------------------------------------------------------------


@dataclass(frozen=True)
class Tone:
    """Art arda çalınan notalardan oluşan kısa bir işaret sesi."""

    notes: tuple[tuple[int, float], ...]
    """(frekans Hz, süre sn) çiftleri."""


TONES: dict[str, Tone] = {
    # Yükselen: "başladım".
    "start": Tone(((660, 0.12), (880, 0.14))),
    # Alçalan: "kaydı kapattım".
    "stop": Tone(((880, 0.12), (660, 0.14))),
    # Daha tiz ve yükselen: "metin hazır".
    "done": Tone(((880, 0.10), (1175, 0.18))),
    # Pes ve uzun: "olmadı".
    "error": Tone(((220, 0.35),)),
}
"""Varsayılan tonlar. Dosya taşımaz, lisans gerektirmez; ffmpeg üretir."""


def tones_dir() -> Path:
    return cache_home() / "pakize" / "tones"


def last_recording_path() -> Path:
    """Son diktenin ses kaydı; her dikte bir öncekinin üzerine yazar.

    Deşifre yanlış çıktığında suçlu mikrofon mu model mi, ancak kayıt
    dinlenerek anlaşılır. Geçici dizin silindiği için bir kopya burada kalır;
    `pakize transcribe` ile yeniden denenebilir.
    """
    return cache_home() / "pakize" / "last-dictation.wav"


def _keep_last_recording(recording: Path) -> None:
    """Kaydın kopyasını önbelleğe alır; başaramazsa dikteyi engellemez."""
    target = last_recording_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(recording, target)
    except OSError:
        return


def tone(name: str, config: Config) -> Path:
    """Bir tonun ses dosyasını döner.

    Config'te o ton için dosya gösterilmişse o kullanılır; yoksa varsayılan
    ton ilk seferde üretilip önbelleğe yazılır.
    """
    custom: Path | None = getattr(config, f"dictate_{name}_sound")
    if custom is not None:
        if not custom.is_file():
            raise DictationError(
                _("dictate_{name}_sound ile gösterilen dosya yok: {path}").format(
                    name=name, path=custom
                )
            )
        return custom

    definition = TONES[name]
    target = tones_dir() / f"{name}-{_tone_fingerprint(definition)}.wav"
    if target.is_file():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    # İki dikte aynı anda üretebilir; yarım dosya çalınmasın diye önce geçici
    # ada yazılıp taşınır. Uzantı sonda kalmalı: ffmpeg biçimi ondan seçer.
    partial = target.with_name(f".{target.stem}.{os.getpid()}{target.suffix}")
    try:
        _render_tone(definition, partial)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _tone_fingerprint(definition: Tone) -> str:
    key = f"{definition.notes}|{TONE_VOLUME}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _render_tone(definition: Tone, target: Path) -> None:
    """Notaları ffmpeg'in sinüs üreteciyle tek bir WAV dosyasına çizer."""
    audio.run_ffmpeg(*_tone_arguments(definition, target))


def _tone_arguments(definition: Tone, target: Path) -> list[str]:
    """Ton için ffmpeg argümanları; test edilebilsin diye ayrı durur."""
    inputs: list[str] = []
    faded: list[str] = []
    for index, (frequency, duration) in enumerate(definition.notes):
        inputs += ["-f", "lavfi", "-i", f"sine=f={frequency}:d={duration}:r=44100"]
        # Her notanın iki ucu yumuşatılır; keskin geçiş "tık" sesi verir.
        fade_out = max(duration - 0.02, 0.0)
        faded.append(
            f"[{index}]afade=t=in:d=0.005,afade=t=out:st={fade_out:.3f}:d=0.02[n{index}]"
        )
    chain = "".join(f"[n{index}]" for index in range(len(definition.notes)))
    graph = ";".join(
        [*faded, f"{chain}concat=n={len(definition.notes)}:v=0:a=1,volume={TONE_VOLUME}[out]"]
    )
    return [*inputs, "-filter_complex", graph, "-map", "[out]", str(target)]


# --- mikrofon ----------------------------------------------------------------


def microphone(config: Config) -> tuple[str, str]:
    """Kayıt aygıtını ffmpeg'in (biçim, aygıt) çifti olarak döner.

    Config'te yazılmamışsa platformun varsayılanı kullanılır. Windows'ta
    varsayılan yoktur: `dshow` aygıtı adıyla ister, ad ise makineden makineye
    değişir.
    """
    spec = config.dictate_microphone or _default_microphone()
    if spec is None:
        raise DictationError(
            _(
                "Windows'ta mikrofon adı gerekli. Aygıtları listele:\n"
                "  ffmpeg -list_devices true -f dshow -i dummy\n"
                "sonra config'e yaz:\n"
                '  dictate_microphone = "dshow:audio=Mikrofon (Realtek Audio)"'
            )
        )

    input_format, separator, device = spec.partition(":")
    if not separator or not input_format or not device:
        raise DictationError(
            _(
                "dictate_microphone 'biçim:aygıt' şeklinde olmalı "
                "(örn. pulse:default, avfoundation::0): {value!r}"
            ).format(value=spec)
        )
    return input_format, device


def _default_microphone() -> str | None:
    if IS_WINDOWS:
        return None
    if IS_MACOS:
        # avfoundation "video:ses" ister; boş video ve ilk ses aygıtı.
        return "avfoundation::0"
    return "pulse:default"


# --- kayıt -------------------------------------------------------------------


class Recorder:
    """Mikrofonu bir WAV dosyasına yazan tek bir `ffmpeg` süreci."""

    def __init__(
        self, destination: Path, input_format: str, device: str, max_seconds: float
    ) -> None:
        self.destination = destination
        self.input_format = input_format
        self.device = device
        self.max_seconds = max_seconds
        self._process: subprocess.Popen | None = None
        self._log: IO[bytes] | None = None
        self._exit_code: int | None = None

    def start(self) -> None:
        command = self._command()
        # Günlük dosyaya yazılır: boru dolarsa ffmpeg yazarken takılır.
        self._log = tempfile.TemporaryFile(prefix="pakize-dictate-")
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._log,
                preexec_fn=die_with_parent(),
            )
        except OSError as exc:
            self._close_log()
            raise DictationError(
                _("Kayıt başlatılamadı: {reason}").format(reason=exc)
            ) from exc

    def running(self) -> bool:
        """Kayıt sürüyor mu? Süre sınırı dolunca ffmpeg kendiliğinden biter."""
        return self._process is not None and self._process.poll() is None

    def stop(self) -> Path:
        """Kaydı kibarca bitirir ve dosyayı döner.

        ffmpeg'e `q` yazılır; böylece dosyanın başlığını tamamlayıp kapanır.
        Sinyalle kesilse başlık eksik kalır, bazı okuyucular dosyayı açamaz.
        Ses gelmediyse ya da ffmpeg açılamadıysa `DictationError` fırlatır.
        """
        self._finish(graceful=True)
        try:
            self._check()
        finally:
            self._close_log()
        return self.destination

    def abort(self) -> None:
        """Kaydı sessizce keser; hata fırlatmaz. Tekrar çağrılabilir."""
        self._finish(graceful=False)
        self._close_log()

    def _command(self) -> list[str]:
        return [
            audio.ffmpeg_binary(),
            "-y", "-hide_banner", "-loglevel", "error", "-nostats",
            "-f", self.input_format,
            "-i", self.device,
            "-ac", "1",
            "-ar", str(SAMPLE_RATE),
            # Emniyet supabı: ikinci basış hiç gelmezse kayıt burada biter.
            "-t", f"{self.max_seconds:g}",
            str(self.destination),
        ]  # fmt: skip

    def _finish(self, graceful: bool) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None and graceful:
            _send_quit(process)
            try:
                process.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        _close_quietly(process.stdin)
        self._exit_code = process.returncode

    def _check(self) -> None:
        size = self.destination.stat().st_size if self.destination.is_file() else 0
        if size > WAV_HEADER_BYTES:
            return
        if self._exit_code not in (0, None):
            raise DictationError(
                _("Kayıt başarısız oldu (ffmpeg çıkış kodu {code}).").format(
                    code=self._exit_code
                )
                + self._log_tail()
            )
        raise DictationError(_("Kayıt boş: mikrofondan ses gelmedi.") + self._log_tail())

    def _log_tail(self) -> str:
        if self._log is None:
            return ""
        self._log.seek(0)
        lines = self._log.read().decode("utf-8", errors="replace").splitlines()
        tail = "\n".join(lines[-LOG_TAIL_LINES:]).strip()
        return f"\n{tail}" if tail else ""

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None


def _send_quit(process: subprocess.Popen) -> None:
    """ffmpeg'e klavyeden `q` basılmış gibi bitirmesini söyler."""
    try:
        process.stdin.write(b"q")
        process.stdin.flush()
    except (OSError, ValueError):
        # Boru kapanmışsa ffmpeg zaten bitiyordur.
        return


def _close_quietly(stream) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except OSError:
        pass


# --- ikinci basış ------------------------------------------------------------


class StopRequest(enum.Enum):
    """İkinci basışın ne bulduğu."""

    NONE = "none"
    """Süren bir dikte yok; bu basış yeni bir dikte başlatmalı."""

    REQUESTED = "requested"
    """Süren dikteye "bitir" dendi."""

    ALREADY = "already"
    """Kayıt zaten bitmiş, deşifre sürüyor; yapılacak bir şey yok."""


def request_stop() -> StopRequest:
    """Süren diktenin kaydını bitirmesini ister.

    Birden çok dikte sürüyorsa hepsine söylenir; kısayol "bitir" demektir,
    "birini bitir" değil.
    """
    pids = runtime.running_pids(runtime.DICTATION_STATE_NAME)
    if not pids:
        return StopRequest.NONE

    outcome = StopRequest.ALREADY
    for pid in pids:
        flag = _stop_flag(pid)
        if not flag.exists():
            flag.touch()
            outcome = StopRequest.REQUESTED
    return outcome


def _stop_flag(pid: int) -> Path:
    return runtime.state_dir(runtime.DICTATION_STATE_NAME) / f"{pid}{STOP_FLAG_SUFFIX}"


@contextlib.contextmanager
def _registered() -> Iterator[Callable[[], bool]]:
    """Süreci dikte kaydına yazar; "bitir" bayrağını yoklayan işlevi verir."""
    pid = os.getpid()
    flag = _stop_flag(pid)
    runtime.register(pid, runtime.DICTATION_STATE_NAME)
    # Aynı numarayı almış eski bir sürecin bayrağı kalmış olabilir.
    flag.unlink(missing_ok=True)
    try:
        yield flag.exists
    finally:
        flag.unlink(missing_ok=True)
        runtime.clear(pid, runtime.DICTATION_STATE_NAME)


# --- akış --------------------------------------------------------------------


def dictate(
    config: Config,
    deliver: Callable[[str], None],
    status: Callable[[str], None] | None = None,
) -> str:
    """Tek bir dikteyi baştan sona yürütür ve metni döner.

    `deliver` metni yerine ulaştırır (ekran, pano); hazır tonu ondan sonra
    çalınır, böylece ton "metin elinde" demektir. `status` ara adımları
    bildirir; kısayoldan çalışırken kimse okumaz, terminalde işe yarar.
    """
    say = status or (lambda message: None)

    # Eksik ayar daha ilk saniyede söylenir; kullanıcı iki dakika konuştuktan
    # sonra değil. Ton dosyaları da aynı sebeple baştan çözülür.
    check_asr_setup(config)
    input_format, device = microphone(config)
    start_tone = tone("start", config)
    stop_tone = tone("stop", config)
    done_tone = tone("done", config)

    with _registered() as stop_requested, tempfile.TemporaryDirectory(
        prefix="pakize-dictate-"
    ) as workdir:
        recorder = Recorder(
            Path(workdir) / "recording.wav",
            input_format,
            device,
            config.dictate_max_seconds,
        )
        audio.play(start_tone)
        recorder.start()
        say(_("Kayıt başladı. Bitirmek için komutu tekrar çalıştır (terminalde Ctrl+C)."))
        try:
            # Sunucu kayıt sürerken yüklenir; kullanıcı konuşurken geçer.
            # "Bitir" isteği yüklemeyi beklemez: kayıt hemen kapanır, hazır
            # olması yalnız deşifreden önce beklenir.
            with launch_asr_server(config) as server:
                _wait_until_finished(recorder, stop_requested)
                recording = recorder.stop()
                audio.play(stop_tone)
                _keep_last_recording(recording)
                say(_("Deşifre ediliyor..."))
                server.wait_ready()
                engine = create_asr_engine(
                    config.asr_engine, replace(config, asr_server_url=server.url)
                )
                text = engine.transcribe(recording)
        finally:
            recorder.abort()

    if not text:
        raise DictationError(_("Kayıtta konuşma bulunamadı."))

    deliver(text)
    audio.play(done_tone)
    return text


def _wait_until_finished(recorder: Recorder, stop_requested: Callable[[], bool]) -> None:
    """Kayıt bitene ya da "bitir" denene kadar bekler.

    Terminalde Ctrl+C ikinci basış sayılır: kayıt biter, deşifre sürer.
    Deşifre sırasında ikinci bir Ctrl+C ise işi keser.
    """
    try:
        while recorder.running() and not stop_requested():
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return


def announce_error(config: Config, message: str) -> None:
    """Hata tonunu çalar, ardından hatanın ilk satırını Pakize'nin sesiyle okur.

    Kısayoldan çalışırken ekran yoktur; kullanıcı neyin ters gittiğini ancak
    duyar. Uyarının kendisi çalınamazsa asıl hatanın önüne geçmez: sessizce
    vazgeçilir, hata zaten ekrana yazılmıştır.
    """
    try:
        audio.play(tone("error", config))
    except (DictationError, audio.AudioError, OSError):
        pass

    first_line = next((line for line in message.splitlines() if line.strip()), "")
    # Okunan cümle sesin diline uyar, arayüzün diline değil: İngilizce
    # ortamda Türkçe sesin İngilizce hata okuması anlaşılmıyor.
    spoken = in_language(first_line.strip() or "Dikte başarısız oldu.", voice_language(config.voice))
    try:
        audio.play(notices.dictation_notice(spoken, config))
    except (EngineError, audio.AudioError, OSError):
        pass
