"""EMA Lightning ile tamamen çevrimdışı Türkçe seslendirme.

EMA Lightning (https://huggingface.co/canberkkkkkk/ema-lightning) yerelde,
CPU'da çalışan tek sesli bir Türkçe TTS modelidir. Piper gibi ağ istemez;
Türkçe doğallığı Piper'ın üstündedir.

Model torch ister ve Pakize'nin çekirdeği ağır makine öğrenmesi bağımlılıkları
taşımaz (bkz. `piper.py`, `asr/qwen.py`). Bu yüzden EMA, kullanıcının ayrıca
kurduğu bir Python ortamında çalışır: `ema_python` o ortamın yorumlayıcısını
gösterir, Pakize `ema_worker.py` betiğini onunla alt süreç olarak başlatır.

Neden parça başına süreç değil, iş başına tek işçi: torch'un ithali ve modelin
yüklenmesi yaklaşık 3 saniye sürer ve süreç başına yarım GB'a yakın bellek
tutar. Boru hattı bir metni onlarca parçaya böldüğü için her parçaya yeni
süreç açmak kabul edilemezdi. İşçi ilk `synthesize` çağrısında tembel
başlatılır, aynı iş içindeki bütün parçalar ona sırayla gider (`asyncio.Lock`)
ve iş bitince boru hattı `aclose` ile onu kapatır — başarıda, hatada ve
iptalde. Sürekli ayakta duran bir şey yoktur (`asr/server.py` ile aynı ilke).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import IO, Any, ClassVar

from ..config import Config
from ..i18n import _
from ..platforms import IS_WINDOWS, die_with_parent
from . import ema_worker
from .base import EngineError, EngineUnavailable, TtsEngine

WORKER_PATH = Path(ema_worker.__file__)
"""Alt süreçte çalışan betik; testler protokolü taklit eden bir sahteyle değiştirir."""

READY_TIMEOUT = 600.0
"""İşçinin hazır olması için azami bekleme (saniye).

Yükleme normalde birkaç saniyedir; ilk kullanımda model indirmesi (yaklaşık
34 MB) yavaş bir bağlantıda dakikalar sürebilir. Cömert bir sınır, gereksiz
bir hatadan iyidir.
"""

STOP_GRACE_SECONDS = 5.0
"""stdin kapanınca işçinin kendi kendine çıkması için tanınan süre."""

LOG_TAIL_LINES = 15
"""İşçi çökerse hata mesajına eklenecek stderr satırı sayısı."""

REQUEST_TIMEOUT_BASE = 60.0
REQUEST_SECONDS_PER_CHAR = 0.1
"""Bir parçanın yanıtı için azami bekleme: taban + karakter başına pay (saniye).

CPU'da gerçek zaman oranı en kötü 0.3 civarı; 2500 karakterlik bir parça
yaklaşık üç dakikalık ses, yani bir dakikadan az sentez demek. Bu formül ona
310 saniye tanır: yük altındaki makinede bile cömert, takılmış işçide ise
sonsuza dek beklemekten iyi.
"""

ENV_DIR_EXAMPLE = "~/.local/share/pakize-ema"

INSTALL_COMMAND = (
    "uv pip install --python {python} ema-lightning==1.0.1 torch "
    "--index https://download.pytorch.org/whl/cpu"
)
"""EMA ortamına paketleri kuran komut; `{python}` ortamın yolu ya da yorumlayıcısı.

`--index` (tek dizin) bilerek: `--index-url` + `--extra-index-url` ikilisinde
uv PyPI'yı öne alır ve torch'un birkaç GB'lık CUDA sürümünü kurar. PyTorch'un
CPU dizini ema-lightning'in diğer bağımlılıklarını da barındırmadığından uv
eksikleri PyPI'dan tamamlar; ölçülen kurulum yaklaşık 400 MB.
"""


class EmaEngine(TtsEngine):
    name: ClassVar[str] = "ema"
    output_suffix: ClassVar[str] = ".wav"

    def __init__(self, config: Config, worker_path: Path | None = None) -> None:
        super().__init__(config)
        self.worker_path = worker_path or WORKER_PATH
        self._worker: _Worker | None = None
        self._lock = asyncio.Lock()
        self._failure: EngineError | None = None
        """İşçi bir kez açılamadıysa ya da öldüyse sonraki parçalar aynı hatayı alır.

        Aksi hâlde kilidi bekleyen her parça yeni bir işçi başlatmayı dener,
        her biri saniyeler ve yüzlerce MB harcayıp aynı hatayla düşerdi.
        """

    def ensure_available(self) -> None:
        """Yalnızca ayarı ve dosyayı yoklar; torch yüklemez, ucuz kalır."""
        python = self.config.ema_python
        if python is None:
            example = _python_example()
            raise EngineUnavailable(
                _(
                    "ema motoru için ayrı bir Python ortamı gerekli. Kurmak için:\n"
                    "  uv venv {env}\n"
                    "  {install}\n"
                    "sonra yorumlayıcının yolunu config'e yaz:\n"
                    '  ema_python = "{example}"'
                ).format(
                    env=ENV_DIR_EXAMPLE,
                    install=INSTALL_COMMAND.format(python=ENV_DIR_EXAMPLE),
                    example=example,
                )
            )
        if not python.is_file():
            raise EngineUnavailable(
                _("ema_python ile gösterilen Python yok: {path}").format(path=python)
            )

    async def synthesize(self, text: str, destination: Path) -> None:
        speed = self._speed()
        request = {
            "text": text,
            "out": str(destination),
            "speed": speed,
            "volume": self.config.volume,
        }
        async with self._lock:
            worker = await self._ensure_worker()
            try:
                response = await worker.request(request, request_timeout(text))
            except EngineError as exc:
                self._failure = exc
                raise

        if not response.get("ok"):
            raise EngineError(
                _("ema seslendirme başarısız: {error}").format(
                    error=response.get("error", "?")
                )
            )
        if not destination.is_file() or destination.stat().st_size == 0:
            raise EngineError(_("ema boş ses dosyası üretti"))

    async def aclose(self) -> None:
        """İşçiyi kapatır; hiç başlamadıysa ya da çoktan kapandıysa bir şey yapmaz."""
        worker, self._worker = self._worker, None
        if worker is not None:
            await worker.stop()

    async def _ensure_worker(self) -> _Worker:
        """İşçiyi ilk ihtiyaçta başlatır; kilit altında çağrılır."""
        if self._failure is not None:
            raise self._failure
        if self._worker is None:
            worker = _Worker(self.config.ema_python, self.worker_path)
            # Önce atanır: açılış yarıda kesilirse `aclose` yarım süreci de görsün.
            self._worker = worker
            try:
                await worker.start()
            except BaseException as exc:
                self._worker = None
                await worker.stop()
                if isinstance(exc, EngineError):
                    self._failure = exc
                raise
        return self._worker

    def _speed(self) -> float:
        """`rate` çarpanını EMA hızına çevirir; aralık dışı değer açık hata verir."""
        rate = self.config.rate
        try:
            return ema_worker.speed_from_rate(rate)
        except ValueError:
            raise EngineError(
                _("rate {rate} EMA için geçersiz; {low} ile {high} arasında olmalı").format(
                    rate=rate, low=ema_worker.SPEED_MIN, high=ema_worker.SPEED_MAX
                )
            ) from None


def request_timeout(text: str) -> float:
    """Parçanın uzunluğuna göre yanıt bekleme süresi (saniye)."""
    return REQUEST_TIMEOUT_BASE + REQUEST_SECONDS_PER_CHAR * len(text)


def _python_example() -> str:
    """Config örneğindeki yorumlayıcı yolu; sanal ortamın düzeni platforma göre değişir."""
    if IS_WINDOWS:
        return f"{ENV_DIR_EXAMPLE}/Scripts/python.exe"
    return f"{ENV_DIR_EXAMPLE}/bin/python"


class _Worker:
    """Tek bir işçi süreci: başlatma, hazır bekleme, istek-yanıt, kapatma."""

    def __init__(self, python: Path, script: Path) -> None:
        self.python = python
        self.script = script
        self.process: asyncio.subprocess.Process | None = None
        self.ready = False
        self._log: IO[bytes] | None = None

    async def start(self) -> None:
        """Süreci açar ve "hazır" satırını bekler; açılamazsa `EngineUnavailable`."""
        # stderr boruya değil dosyaya yazılır: torch'un gürültüsü boruyu
        # doldurursa işçi yazarken takılır, kimse okumadığı için de çözülmez.
        self._log = tempfile.TemporaryFile(prefix="pakize-ema-")
        try:
            self.process = await asyncio.create_subprocess_exec(
                str(self.python),
                "-I",
                str(self.script),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self._log,
                preexec_fn=die_with_parent(),
            )
        except OSError as exc:
            raise EngineUnavailable(
                _("EMA işçisi başlatılamadı: {error}").format(error=exc)
            ) from exc

        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), READY_TIMEOUT)
        except asyncio.TimeoutError:
            raise EngineUnavailable(
                _("EMA işçisi {seconds:.0f} sn içinde hazır olmadı.").format(
                    seconds=READY_TIMEOUT
                )
                + self._log_tail()
            ) from None

        if not line:
            await self.process.wait()
            raise EngineUnavailable(
                _("EMA işçisi açılırken kapandı (çıkış kodu {code}).").format(
                    code=self.process.returncode
                )
                + self._log_tail()
            )

        message = _parse(line)
        if not message.get("ready"):
            raise EngineUnavailable(_setup_message(message, self.python) + self._log_tail())
        self.ready = True

    async def request(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Bir isteği yazar, yanıt satırını döner.

        İşçi ölmüşse ya da `timeout` saniye içinde yanıt vermezse `EngineError`;
        takılan işçi kapatılır ki geride süreç kalmasın.
        """
        process = self.process
        assert process is not None and process.stdin is not None
        try:
            process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
            await process.stdin.drain()
            line = await asyncio.wait_for(process.stdout.readline(), timeout)
        except (BrokenPipeError, ConnectionResetError):
            line = b""
        except asyncio.TimeoutError:
            await self.stop()
            raise EngineError(
                _("EMA işçisi {seconds:.0f} sn içinde yanıt vermedi; kapatıldı.").format(
                    seconds=timeout
                )
            ) from None

        if not line:
            await process.wait()
            raise EngineError(
                _("EMA işçisi seslendirme sırasında kapandı (çıkış kodu {code}).").format(
                    code=process.returncode
                )
                + self._log_tail()
            )
        return _parse(line)

    async def stop(self) -> None:
        """İşçiyi kapatır. Tekrar çağrılabilir.

        Hazır bir işçi stdin kapanınca kendisi çıkar; henüz model yükleyen bir
        işçi stdin'i okumadığı için doğrudan sonlandırılır (iptalde 3 saniyelik
        yüklemenin bitmesini beklemeye değmez). İkisi de süresinde çıkmazsa
        öldürülür.
        """
        process, self.process = self.process, None
        try:
            if process is not None and process.returncode is None:
                if self.ready and process.stdin is not None:
                    process.stdin.close()
                else:
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        except BaseException:
            # Kapanış da kesilirse (ikinci Ctrl+C) süreç sahipsiz kalmasın.
            if process is not None and process.returncode is None:
                process.kill()
            raise
        finally:
            self._close_log()

    def _log_tail(self) -> str:
        """İşçinin stderr'inin son satırları; hatanın sebebi çoğunlukla oradadır."""
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


def _parse(line: bytes) -> dict[str, Any]:
    """Protokol satırını çözer; JSON değilse ham metni hata olarak sarar."""
    try:
        message = json.loads(line)
    except ValueError:
        return {"ok": False, "ready": False, "error": line.decode(errors="replace").strip()}
    if not isinstance(message, dict):
        return {"ok": False, "ready": False, "error": line.decode(errors="replace").strip()}
    return message


def _setup_message(message: dict[str, Any], python: Path) -> str:
    """İşçinin açılış hatasını kullanıcı diline çevirir.

    İşçi `pakize`'yi ithal edemediği için çeviri yapamaz; kısa bir `code`
    gönderir, metin burada kurulur. Tanınmayan kod ham hatayı gösterir.
    """
    code = message.get("code")
    error = message.get("error", "")
    install = INSTALL_COMMAND.format(python=python)
    if code == "missing_package":
        # Gösterilen yorumlayıcı sistem Python'u olabilir; torch'u oraya değil
        # ayrı bir ortama kurmayı öneririz.
        return _(
            "EMA ortamında ({python}) gerekli paketler yok: {error}\n"
            "Ayrı bir ortam açıp paketleri oraya kur:\n"
            "  uv venv {env}\n"
            "  {install}\n"
            "sonra yorumlayıcının yolunu config'e yaz:\n"
            '  ema_python = "{example}"'
        ).format(
            python=python,
            error=error,
            env=ENV_DIR_EXAMPLE,
            install=INSTALL_COMMAND.format(python=ENV_DIR_EXAMPLE),
            example=_python_example(),
        )
    if code == "wrong_version":
        return _(
            "ema-lightning {installed} kurulu; güvenli yükleme için tam olarak "
            "{required} gerekli. Kurmak için:\n  {install}"
        ).format(
            installed=message.get("installed", "?"),
            required=ema_worker.REQUIRED_VERSION,
            install=install,
        )
    if code == "download_failed":
        return _(
            "EMA model dosyaları indirilemedi (ilk kullanımda ağ gerekir): {error}"
        ).format(error=error)
    if code == "checksum_mismatch":
        return _(
            "EMA model dosyası beklenen sha256 ile uyuşmuyor: {file}. "
            "Dosya değişmiş olabilir; model yüklenmedi."
        ).format(file=message.get("file", "?"))
    if code == "load_failed":
        return _("EMA modeli yüklenemedi: {error}").format(error=error)
    return _("EMA işçisi başlatılamadı: {error}").format(error=error)
