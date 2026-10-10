"""antalia-mini işçisi — Pakize'nin ayrı bir Python ortamında çalıştırdığı betik.

Bu dosya `pakize`'yi İTHAL ETMEZ (bkz. `ema_worker.py` baş yorumu): yalnızca
standart kütüphane, torch, numpy ve antalia_mini kullanır. Pakize onu
`[antalia_mini_python, "-I", <bu dosya>]` ile başlatır. Ses yardımcıları EMA
işçisiyle ortak `worker_audio.py`'dedir; `-I` betik dizinini yoldan çıkardığı
için dizin ithal süresince `sys.path`'e açıkça eklenir.

Protokol EMA'nınkiyle aynıdır; yalnız istek `speed` değil `rate` taşır,
çünkü hız eşlemesi modelin kendi varsayılan hızını ister:

    açılış   → {"ready": true}
             | {"ready": false, "code": "...", "error": "..."}  (ve çıkış)
    istek    → {"text": "...", "out": "/yol/parca.wav", "rate": 1.15, "volume": 1.0}
    yanıt    → {"ok": true} | {"ok": false, "error": "..."}

Güvenlik: antalia-mini ağırlıkları safetensors'tır, çıkarımda pickle yoktur.
Model sabit bir revizyondan açılır ve iki ağırlık dosyasının sha256'sı
buradaki sabitlerle doğrulanır; uyuşmazsa işçi hazır olmadan çıkar. Paketin
`say(speed=...)` sözleşmesine dayanıldığı için sürüm tam olarak 1.0.0 değilse
işçi başlamayı reddeder.

Kesme işaretleri silinmez: antalia'nın metin düzenleyicisi `EMA'nın` gibi
ifadeleri kendisi çözüyor; EMA'nın `prepare_text`'i burada kullanılmaz.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO

_HERE = str(Path(__file__).resolve().parent)
sys.path.insert(0, _HERE)
try:
    from worker_audio import render_pcm, write_wav
finally:
    sys.path.remove(_HERE)

REQUIRED_VERSION = "1.0.0"
"""İşçinin `say` sözleşmesine güvendiği tek antalia-mini sürümü."""

REPO_ID = "cloud0day3/antalia-mini"
REVISION = "1e8166a7436f3e11f7f03b339258ec30f366db60"
"""Model dosyalarının alındığı sabit Hugging Face revizyonu (commit)."""

CHECKSUMS: dict[str, str] = {
    "acoustic.safetensors": "72c36a6855ce95dc1d35960a7b61515136813313406e5b9ae1c2ebe6cd2ad428",
    "vocoder.safetensors": "89ca374cc55864b38a36f9ea87c41e1b17376e5d6d68e3a0458332861509bbf6",
}
"""Sabit revizyondaki ağırlık dosyalarının sha256'ları; uyuşmayan dosyayla işçi başlamaz."""

SEED = 0
"""Sabit tohum: aynı metin her seferinde aynı sesi versin."""


class SetupError(Exception):
    """Açılışta modelin hazırlanmasını engelleyen hata.

    `code` Pakize tarafında kullanıcı diline çevrilen kısa bir anahtardır;
    `detail` serbest metindir (sürüm, dosya adı, istisna metni).
    """

    def __init__(self, code: str, detail: str = "", **extra: Any) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        self.extra = extra

    def as_message(self) -> dict[str, Any]:
        return {"ready": False, "code": self.code, "error": self.detail, **self.extra}


# --- saf mantık: torch'suz test edilir ---------------------------------------


def check_version(installed: str | None) -> None:
    """Kurulu antalia-mini sürümünü denetler; 1.0.0 dışını reddeder."""
    if installed is None:
        raise SetupError("missing_package", "antalia-mini is not installed")
    if installed != REQUIRED_VERSION:
        raise SetupError(
            "wrong_version",
            f"antalia-mini {installed} installed, {REQUIRED_VERSION} required",
            installed=installed,
        )


def installed_version(distribution: str = "antalia-mini") -> str | None:
    """Kurulu paket sürümü; paket yoksa None."""
    from importlib import metadata

    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksum(path: Path, name: str) -> None:
    """Dosyanın sha256'sı beklenenle uyuşmazsa `SetupError` fırlatır."""
    actual = sha256_of(path)
    if actual != CHECKSUMS[name]:
        raise SetupError(
            "checksum_mismatch",
            f"{name}: expected sha256 {CHECKSUMS[name]}, got {actual}",
            file=name,
        )


def verify_release(directory: Path) -> None:
    """Açılan sürüm dizinindeki iki ağırlık dosyasını sabitlerle doğrular."""
    for name in CHECKSUMS:
        verify_checksum(directory / name, name)


def speed_for(rate: float, default_speed: float) -> float | None:
    """Pakize'nin `rate` çarpanını antalia'nın `speed` değerine çevirir.

    İkisi de "1'den büyük = daha hızlı" demek. Modelin kendi varsayılan hızı
    (sürüm config'inde 0.95) dinlenerek seçilmiş; `rate` 1.0 iken ona
    dokunulmaz (`None` = paket varsayılanı), aksi hâlde varsayılan `rate` ile
    çarpılır. Pozitif olmayan değer sessizce varsayılana düşmez, hata verir.
    """
    if rate <= 0:
        raise ValueError(f"rate {rate} must be positive")
    if rate == 1.0:
        return None
    return default_speed * rate


# --- model ---------------------------------------------------------------------


def prepare_model():
    """Sürümü denetler, modeli sabit revizyondan açar, ağırlıkları doğrular."""
    check_version(installed_version())
    try:
        from antalia_mini import Antalia
    except ImportError as exc:  # torch ya da numpy eksik kurulmuş
        raise SetupError("missing_package", f"{exc}") from exc

    try:
        tts = Antalia(revision=REVISION, warmup=False)
    except ImportError as exc:
        raise SetupError("missing_package", f"{exc}") from exc
    except OSError as exc:  # ağ ve dosya hataları (urllib ve huggingface_hub) buradan türer
        raise SetupError("download_failed", f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise SetupError("load_failed", f"{type(exc).__name__}: {exc}") from exc

    verify_release(Path(tts.path))
    return tts


# --- sentez ------------------------------------------------------------------


def synthesize(tts: Any, request: dict[str, Any]) -> None:
    """Tek bir isteği seslendirip WAV olarak yazar; kesme işaretlerine dokunmaz."""
    speed = speed_for(float(request.get("rate", 1.0)), float(tts.defaults["speed"]))
    volume = float(request.get("volume", 1.0))
    result = tts.say(request["text"], seed=SEED, speed=speed)
    sample_rate = int(result.sample_rate)
    write_wav(Path(request["out"]), render_pcm(result.audio, volume, sample_rate), sample_rate)


def claim_stdout() -> TextIO:
    """Protokol için gerçek stdout'u ayırır; sonrasında stdout stderr'e akar.

    Hem `sys.stdout` hem de 1 numaralı dosya tanıtıcısı yönlendirilir: C
    tarafından yazan kütüphaneler Python nesnesini değil tanıtıcıyı kullanır.
    stderr UTF-8'e alınır (Windows'ta yerel kod sayfasıyla açılır; Pakize
    kuyruğu UTF-8 okur). `-I` PYTHONIOENCODING'i yok saydığı için burada.
    """
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    utf8_stderr()
    sys.stdout = sys.stderr
    return protocol


def utf8_stderr() -> None:
    """`sys.stderr`'i platformdan bağımsız UTF-8'e alır; akış yoksa dokunmaz."""
    stream = sys.stderr
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def send(channel: TextIO, message: dict[str, Any]) -> None:
    channel.write(json.dumps(message) + "\n")
    channel.flush()


def serve(tts: Any, channel: TextIO, requests: Iterable[bytes]) -> None:
    """İstekleri sırayla işler; stdin kapanınca döner."""
    for raw in requests:
        if not raw.strip():
            continue
        try:
            synthesize(tts, json.loads(raw))
        except Exception as exc:  # hata işçiyi düşürmez, yanıt olarak döner
            send(channel, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            continue
        send(channel, {"ok": True})


def main() -> int:
    channel = claim_stdout()
    try:
        tts = prepare_model()
    except SetupError as exc:
        send(channel, exc.as_message())
        return 1
    send(channel, {"ready": True})
    serve(tts, channel, iter(sys.stdin.buffer.readline, b""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
