"""Deşifre sunucusunun ömrü.

Tasarım şartı: sürekli ayakta duran hiçbir şey olmayacak. Sunucu yüklü
modelle birkaç GB bellek tutuyor; bu yüzden ömrü tek bir işin ömrü kadardır. `asr_server`
ile açılan blok bitince — iş başarılı olsun, hata versin ya da Ctrl+C ile
kesilsin — sunucu kapanır. `SIGTERM` de buna dahil: Python onu varsayılan
olarak `finally` çalıştırmadan uygular, bu yüzden blok süresince çıkış
istisnasına çevrilir. Pakize'nin kendisi `kill -9` ile öldürülürse Linux'ta
çekirdek sunucuyu da kapatır (`platforms.die_with_parent`).

Dışarıda çalışan bir sunucu (`asr_server_url`) varsa Pakize ona dokunmaz:
onun ömrü kullanıcınındır.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO, Iterator

from ..config import Config
from ..i18n import _
from ..platforms import die_with_parent
from .base import AsrError, AsrUnavailable

DEFAULT_BINARY = "llama-server"

HOST = "127.0.0.1"
"""Sunucu yalnız bu makineden erişilebilir; ağa açılmaz."""

CONTEXT_SIZE = 8192
"""Bağlam penceresi; dakikalarca süren bir kaydın sesine yetiyor."""

READY_TIMEOUT = 120.0
"""Modelin yüklenmesi için azami bekleme (saniye).

Yükleme genellikle birkaç saniye sürer; yük altındaki bir makinede
katlanabilir. Cömert bir sınır, gereksiz bir hatadan iyidir.
"""

READY_POLL_SECONDS = 0.25

STOP_GRACE_SECONDS = 5.0
"""Kibarca kapanması için tanınan süre; sonra zorla kapatılır."""

LOG_TAIL_LINES = 15
"""Sunucu çökerse hata mesajına eklenecek günlük satırı sayısı."""


@contextlib.contextmanager
def asr_server(config: Config) -> Iterator[str]:
    """Deşifre sunucusunun adresini verir; gerekiyorsa sunucuyu açıp kapatır.

    `asr_server_url` doluysa o adres olduğu gibi verilir. Boşsa ve
    `asr_model` tanımlıysa sunucu başlatılır, blok bitince kapatılır.
    """
    if config.asr_server_url:
        yield config.asr_server_url
        return

    _require_model(config)
    with _termination_as_exit():
        server = LlamaServer(config)
        server.start()
        try:
            yield server.url
        finally:
            server.stop()


def check_asr_setup(config: Config) -> None:
    """Sunucuyu başlatmadan, başlatılabileceğini doğrular.

    Dikte, kayda başlamadan önce sorar: kullanıcı iki dakika konuştuktan
    sonra "model yok" demek yerine, eksik ayar daha ilk saniyede söylenir.
    Hiçbir süreç açılmaz; yalnız ayarlar ve dosyalar yoklanır.
    """
    if config.asr_server_url:
        return
    _require_model(config)
    LlamaServer(config).resolve_paths()


def _require_model(config: Config) -> None:
    if config.asr_model is not None:
        return
    raise AsrUnavailable(
        _(
            "Deşifre için bir sunucu gerekli. Config'e ya model yolunu ekle "
            "(Pakize sunucuyu kendisi açıp kapatır):\n"
            '  asr_model = "/yol/model.gguf"\n'
            '  asr_mmproj = "/yol/mmproj.gguf"\n'
            "ya da çalışan bir sunucunun adresini:\n"
            '  asr_server_url = "http://127.0.0.1:8099"'
        )
    )


@contextlib.contextmanager
def _termination_as_exit() -> Iterator[None]:
    """Blok süresince sonlandırma sinyallerini `SystemExit`'e çevirir.

    Python `SIGTERM`'ü ve `SIGHUP`'ı varsayılan olarak `finally` blokları
    çalışmadan uygular; sunucu o zaman sahipsiz kalıp belleği tutardı.
    `pakize stop`, oturumun kapanması ve terminalin kapatılması bu yoldan
    gelir. Sinyal işleyicisi yalnız ana iş parçacığında kurulabilir.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(signum, frame):
        raise SystemExit(128 + signum)

    signals = [
        sig
        for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None))
        if sig is not None
    ]
    previous = {sig: signal.signal(sig, handler) for sig in signals}
    try:
        yield
    finally:
        for sig, old_handler in previous.items():
            signal.signal(sig, old_handler)


class LlamaServer:
    """Pakize'nin başlatıp kapattığı tek bir `llama-server` süreci."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.url = ""
        self._process: subprocess.Popen | None = None
        self._log: IO[bytes] | None = None

    def start(self) -> None:
        """Sunucuyu başlatır ve model yüklenene kadar bekler.

        Beklerken hata olursa sunucu kapatılarak çıkılır; yarım açılmış bir
        sunucu geride kalmaz.
        """
        command = self._command()
        # Günlük boruya değil dosyaya yazılır: boru dolarsa sunucu yazarken
        # takılır, kimse okumadığı için de bir daha çözülmez.
        self._log = tempfile.TemporaryFile(prefix="pakize-asr-")
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                preexec_fn=die_with_parent(),
            )
        except OSError as exc:
            self._close_log()
            raise AsrError(
                _("Deşifre sunucusu başlatılamadı: {reason}").format(reason=exc)
            ) from exc

        try:
            self._wait_ready()
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Sunucuyu kapatır; kibar kapanmazsa zorla kapatır. Tekrar çağrılabilir."""
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._close_log()

    def resolve_paths(self) -> tuple[str, Path, Path]:
        """Çalıştırılabilir, model ve ses kodlayıcısının yollarını doğrular.

        Eksik ya da yanlış olan varsa `AsrUnavailable` fırlatır.
        """
        model = _existing_file(self.config.asr_model, "asr_model")
        if self.config.asr_mmproj is None:
            raise AsrUnavailable(
                _(
                    "Model sesi okuyabilmek için ses kodlayıcısına ihtiyaç duyar. "
                    "Config'e ekle:\n"
                    '  asr_mmproj = "/yol/mmproj.gguf"'
                )
            )
        mmproj = _existing_file(self.config.asr_mmproj, "asr_mmproj")
        return self._binary(), model, mmproj

    def _command(self) -> list[str]:
        binary, model, mmproj = self.resolve_paths()

        port = _free_port()
        self.url = f"http://{HOST}:{port}"
        return [
            binary,
            "--model", str(model),
            "--mmproj", str(mmproj),
            "--threads", str(os.cpu_count() or 4),
            "--ctx-size", str(CONTEXT_SIZE),
            "--host", HOST,
            "--port", str(port),
            "--offline",
            "--no-webui",
        ]  # fmt: skip

    def _binary(self) -> str:
        configured = self.config.asr_server_binary
        if configured is not None:
            return str(_existing_file(configured, "asr_server_binary"))

        found = shutil.which(DEFAULT_BINARY)
        if found is None:
            raise AsrUnavailable(
                _(
                    "llama-server bulunamadı. llama.cpp sürümlerinden indirilebilir:\n"
                    "  https://github.com/ggml-org/llama.cpp/releases\n"
                    'Kuruluysa yolunu config\'e yaz: asr_server_binary = "/yol/llama-server"'
                )
            )
        return found

    def _wait_ready(self) -> None:
        """Model yüklenip istek kabul edilene kadar bekler.

        `/health` model yüklenirken de "ok" diyebiliyor; `/v1/models` ancak
        model hazır olunca yanıt veriyor, bu yüzden ona sorulur.
        """
        deadline = time.monotonic() + READY_TIMEOUT
        while True:
            exit_code = self._process.poll()
            if exit_code is not None:
                raise AsrError(
                    _("Deşifre sunucusu açılırken kapandı (çıkış kodu {code}).").format(
                        code=exit_code
                    )
                    + self._log_tail()
                )
            if _responds(self.url + "/v1/models"):
                return
            if time.monotonic() >= deadline:
                raise AsrError(
                    _("Deşifre sunucusu {seconds:.0f} sn içinde hazır olmadı.").format(
                        seconds=READY_TIMEOUT
                    )
                    + self._log_tail()
                )
            time.sleep(READY_POLL_SECONDS)

    def _log_tail(self) -> str:
        """Sunucu günlüğünün son satırları; hatanın sebebi çoğunlukla oradadır."""
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


def _existing_file(path: Path, setting: str) -> Path:
    if not path.is_file():
        raise AsrUnavailable(
            _("{setting} ile gösterilen dosya yok: {path}").format(
                setting=setting, path=path
            )
        )
    return path


def _free_port() -> int:
    """İşletim sisteminden boş bir port ister.

    Port kapatılıp sunucuya verilene kadar başka biri alabilir; o durumda
    sunucu açılırken kapanır ve günlüğüyle birlikte anlaşılır bir hata çıkar.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False
