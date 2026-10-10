"""Ayrı bir Python ortamında çalışan işçi süreçli motorların ortak gövdesi.

torch isteyen motorlar (EMA, antalia-mini) Pakize'nin ortamında çalışmaz; kullanıcının
ayrıca kurduğu bir ortamın yorumlayıcısı, motorun işçi betiğini `-I` ile alt
süreç olarak çalıştırır. Burada motordan bağımsız olan her şey durur: sürecin
açılması ve "hazır" beklenmesi, satır başına JSON istek-yanıt, zaman aşımı,
kapanış, stderr kuyruğu ve iş başına tek işçi düzeni. Motora özgü olan (config
anahtarı, kurulum komutları, isteğin alanları) `ema.py` ve `antalia.py`'dedir.

Neden parça başına süreç değil, iş başına tek işçi: torch'un ithali ve modelin
yüklenmesi saniyeler sürer ve süreç başına yüzlerce MB bellek tutar. Boru hattı
bir metni onlarca parçaya böldüğü için her parçaya yeni süreç açmak kabul
edilemezdi. İşçi ilk `synthesize` çağrısında tembel başlatılır, aynı iş
içindeki bütün parçalar ona sırayla gider (`asyncio.Lock`) ve iş bitince boru
hattı `aclose` ile onu kapatır — başarıda, hatada ve iptalde. Sürekli ayakta
duran bir şey yoktur (`asr/server.py` ile aynı ilke).
"""

from __future__ import annotations

import abc
import asyncio
import json
import tempfile
from pathlib import Path
from typing import IO, Any, Callable, ClassVar

from ..config import Config
from ..i18n import _
from ..platforms import IS_WINDOWS, die_with_parent
from .base import EngineError, EngineUnavailable, TtsEngine

READY_TIMEOUT = 600.0
"""İşçinin hazır olması için azami bekleme (saniye).

Yükleme normalde birkaç saniyedir; ilk kullanımda model indirmesi (on MB'lar)
yavaş bir bağlantıda dakikalar sürebilir. Cömert bir sınır, gereksiz bir
hatadan iyidir.
"""

STOP_GRACE_SECONDS = 5.0
"""stdin kapanınca işçinin kendi kendine çıkması için tanınan süre."""

KILL_GRACE_SECONDS = 1.0
"""Sonlandırma sinyalinden sonra, öldürmeden önce tanınan süre."""

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


def request_timeout(text: str) -> float:
    """Parçanın uzunluğuna göre yanıt bekleme süresi (saniye)."""
    return REQUEST_TIMEOUT_BASE + REQUEST_SECONDS_PER_CHAR * len(text)


def startup_failure(label: str, error: str) -> str:
    """İşçinin tanınmayan bir sebeple açılamadığını söyleyen mesaj."""
    return _("{engine} işçisi başlatılamadı: {error}").format(engine=label, error=error)


def python_example(env_dir: str) -> str:
    """Config örneğindeki yorumlayıcı yolu; sanal ortamın düzeni platforma göre değişir."""
    if IS_WINDOWS:
        return f"{env_dir}/Scripts/python.exe"
    return f"{env_dir}/bin/python"


class WorkerEngine(TtsEngine):
    """İşçi süreçli motorların ortak gövdesi: tek işçi, kilit, hata hafızası, kapanış.

    Alt sınıf motorun adını (`name`), hata mesajlarındaki etiketini (`label`),
    config anahtarını (`config_key`), yorumlayıcıyı (`_python`) ve kurulum
    mesajlarını (`_setup_message`) verir; `synthesize` isteği kurup `_run`'a
    bırakır.
    """

    label: ClassVar[str]
    """Hata mesajlarında görünen motor adı ("EMA", "antalia-mini")."""

    config_key: ClassVar[str]
    """Yorumlayıcı yolunu tutan config anahtarı ("ema_python", "antalia_mini_python")."""

    output_suffix: ClassVar[str] = ".wav"

    def __init__(self, config: Config, worker_path: Path) -> None:
        super().__init__(config)
        self.worker_path = worker_path
        self._worker: Worker | None = None
        self._lock = asyncio.Lock()
        self._failure: EngineError | None = None
        """İşçi bir kez açılamadıysa ya da öldüyse sonraki parçalar aynı hatayı alır.

        Aksi hâlde kilidi bekleyen her parça yeni bir işçi başlatmayı dener,
        her biri saniyeler ve yüzlerce MB harcayıp aynı hatayla düşerdi.
        """

    def ensure_available(self) -> None:
        """Yalnızca ayarı ve dosyayı yoklar; torch yüklemez, ucuz kalır."""
        python = self._python()
        if not python.is_file():
            raise EngineUnavailable(
                _("{key} ile gösterilen Python yok: {path}").format(
                    key=self.config_key, path=python
                )
            )

    @abc.abstractmethod
    def _python(self) -> Path:
        """Config'teki yorumlayıcı yolu; ayarlanmamışsa kurulum adımlarıyla `EngineUnavailable`."""

    def _setup_message(self, message: dict[str, Any], python: Path) -> str:
        """İşçinin açılış hatasını kullanıcı diline çevirir.

        İşçi `pakize`'yi ithal edemediği için çeviri yapamaz; kısa bir `code`
        gönderir, metin burada kurulur. Motordan bağımsız kodlar burada, kurulum
        komutu isteyenler (`missing_package`, `wrong_version`) alt sınıfta.
        Tanınmayan kod ham hatayı gösterir.
        """
        code = message.get("code")
        error = message.get("error", "")
        if code == "download_failed":
            return _(
                "{engine} model dosyaları indirilemedi (ilk kullanımda ağ gerekir): {error}"
            ).format(engine=self.label, error=error)
        if code == "checksum_mismatch":
            return _(
                "{engine} model dosyası beklenen sha256 ile uyuşmuyor: {file}. "
                "Dosya değişmiş olabilir; model yüklenmedi."
            ).format(engine=self.label, file=message.get("file", "?"))
        if code == "load_failed":
            return _("{engine} modeli yüklenemedi: {error}").format(
                engine=self.label, error=error
            )
        return startup_failure(self.label, error)

    async def _run(self, request: dict[str, Any], text: str, destination: Path) -> None:
        """İsteği işçiye sırayla gönderir, yanıtı ve dosyayı denetler."""
        async with self._lock:
            worker = await self._ensure_worker()
            try:
                response = await worker.request(request, request_timeout(text))
            except EngineError as exc:
                self._failure = exc
                raise

        if not response.get("ok"):
            raise EngineError(
                _("{engine} seslendirme başarısız: {error}").format(
                    engine=self.label, error=response.get("error", "?")
                )
            )
        if not destination.is_file() or destination.stat().st_size == 0:
            raise EngineError(
                _("{engine} boş ses dosyası üretti").format(engine=self.label)
            )

    async def aclose(self) -> None:
        """İşçiyi kapatır; hiç başlamadıysa ya da çoktan kapandıysa bir şey yapmaz."""
        worker, self._worker = self._worker, None
        if worker is not None:
            await worker.stop()

    async def _ensure_worker(self) -> Worker:
        """İşçiyi ilk ihtiyaçta başlatır; kilit altında çağrılır."""
        if self._failure is not None:
            raise self._failure
        if self._worker is None:
            worker = Worker(self._python(), self.worker_path, self.label, self._setup_message)
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


class Worker:
    """Tek bir işçi süreci: başlatma, hazır bekleme, istek-yanıt, kapatma."""

    def __init__(
        self,
        python: Path,
        script: Path,
        label: str,
        setup_message: Callable[[dict[str, Any], Path], str],
    ) -> None:
        self.python = python
        self.script = script
        self.label = label
        self.setup_message = setup_message
        self.process: asyncio.subprocess.Process | None = None
        self.ready = False
        self._log: IO[bytes] | None = None

    async def start(self) -> None:
        """Süreci açar ve "hazır" satırını bekler; açılamazsa `EngineUnavailable`."""
        # stderr boruya değil dosyaya yazılır: torch'un gürültüsü boruyu
        # doldurursa işçi yazarken takılır, kimse okumadığı için de çözülmez.
        self._log = tempfile.TemporaryFile(prefix=f"pakize-{self.label.lower()}-")
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
            raise EngineUnavailable(startup_failure(self.label, str(exc))) from exc

        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), READY_TIMEOUT)
        except asyncio.TimeoutError:
            raise EngineUnavailable(
                _("{engine} işçisi {seconds:.0f} sn içinde hazır olmadı.").format(
                    engine=self.label, seconds=READY_TIMEOUT
                )
                + self._log_tail()
            ) from None

        if not line:
            await self.process.wait()
            raise EngineUnavailable(
                _("{engine} işçisi açılırken kapandı (çıkış kodu {code}).").format(
                    engine=self.label, code=self.process.returncode
                )
                + self._log_tail()
            )

        message = _parse(line)
        if not message.get("ready"):
            raise EngineUnavailable(self.setup_message(message, self.python) + self._log_tail())
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
            # Kuyruk kapanıştan önce okunur: `stop` günlüğü kapatır. Takılmış
            # işçi stdin'i okumadığından kibar kapanış beklenmez, sonlandırılır.
            tail = self._log_tail()
            await self.stop(graceful=False)
            raise EngineError(
                _("{engine} işçisi {seconds:.0f} sn içinde yanıt vermedi; kapatıldı.").format(
                    engine=self.label, seconds=timeout
                )
                + tail
            ) from None

        if not line:
            await process.wait()
            raise EngineError(
                _("{engine} işçisi seslendirme sırasında kapandı (çıkış kodu {code}).").format(
                    engine=self.label, code=process.returncode
                )
                + self._log_tail()
            )
        return _parse(line)

    async def stop(self, graceful: bool = True) -> None:
        """İşçiyi kapatır. Tekrar çağrılabilir.

        Hazır bir işçi stdin kapanınca kendisi çıkar; henüz model yükleyen ya
        da takılmış (`graceful=False`) bir işçi stdin'i okumadığı için doğrudan
        sonlandırılır — iptalde yüklemenin bitmesini, zaman aşımında da kibar
        kapanışı beklemeye değmez. Süresinde çıkmayan öldürülür.
        """
        process, self.process = self.process, None
        try:
            if process is not None and process.returncode is None:
                if graceful and self.ready and process.stdin is not None:
                    process.stdin.close()
                    grace = STOP_GRACE_SECONDS
                else:
                    process.terminate()
                    grace = KILL_GRACE_SECONDS
                try:
                    await asyncio.wait_for(process.wait(), grace)
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
