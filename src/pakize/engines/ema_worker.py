"""EMA Lightning işçisi — Pakize'nin ayrı bir Python ortamında çalıştırdığı betik.

Bu dosya `pakize`'yi İTHAL ETMEZ. Pakize'nin ortamında torch yoktur ve
olmayacaktır (bkz. `piper.py` ve `asr/qwen.py` baş yorumları); EMA'nın
ortamında ise `pakize` yoktur. Betik bu yüzden iki tarafa da bağlı değildir:
yalnızca standart kütüphane, torch, numpy, ema_lightning ve huggingface_hub
kullanır. Pakize onu `[ema_python, "-I", <bu dosya>]` ile başlatır.

Protokol: stdin'den satır başına bir JSON istek, stdout'a satır başına bir
JSON yanıt.

    açılış   → {"ready": true}
             | {"ready": false, "code": "...", "error": "..."}  (ve çıkış)
    istek    → {"text": "...", "out": "/yol/parca.wav", "speed": 1.15, "volume": 1.0}
    yanıt    → {"ok": true} | {"ok": false, "error": "..."}

torch ve kütüphaneler stdout'a gürültü yazar; protokolü bozmasın diye gerçek
stdout açılışta ayrılır, `sys.stdout` ve 1 numaralı dosya tanıtıcısı stderr'e
yönlendirilir. Pakize hata durumunda stderr'in sonunu kullanıcıya gösterir.

Güvenlik: ema-lightning 1.0.1 modeli `torch.load(weights_only=False)` ile
açar; bu, pickle içindeki kodun çalışmasına izin verir. Ayrıca dosyaları Hugging
Face'ten sürüm sabitlemeden indirir. Burada ikisi de devre dışıdır: dosyalar
sabit bir revizyondan indirilir, sha256'ları doğrulanır ve `torch.load` her
zaman `weights_only=True` ile çağrılır. Bu güvenli yol paketin iç
fonksiyonlarına dayandığı için sürüm tam olarak 1.0.1 değilse işçi yüklemeyi
reddeder.

Saf mantık (sürüm denetimi, sha256, hız eşlemesi) torch'suz test edilebilsin
diye ağır kütüphaneler yalnızca ihtiyaç duyan fonksiyonların içinde ithal
edilir. Ses yardımcıları (normalizasyon, parça sonu, WAV) antalia işçisiyle
ortak `worker_audio.py`'dedir; `-I` betik dizinini yoldan çıkardığı için dizin
ithal süresince `sys.path`'e açıkça eklenir.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

_HERE = str(Path(__file__).resolve().parent)
sys.path.insert(0, _HERE)
try:
    from worker_audio import SAMPLE_RATE, render_pcm, write_wav
finally:
    sys.path.remove(_HERE)

REQUIRED_VERSION = "1.0.1"
"""Güvenli yükleyicinin iç fonksiyonlarına güvendiği tek ema-lightning sürümü."""

REPO_ID = "canberkkkkkk/ema-lightning"
REVISION = "7a6ba1ad216bb2f1da9863f80ac8770a6a807632"
"""Model dosyalarının indirildiği sabit Hugging Face revizyonu (commit)."""

CHECKSUMS: dict[str, str] = {
    "ema.pt": "95aec03dafbe0e1d69bca774ab597c779464729a14bc99bfcb52480090c7dfe6",
    "decoder.pt": "9595819b173f411340f63d11332695121a97f8bf1f6d8b6fef0b21cf99c7ad67",
    "config.json": "27546c470dd4e86d9ab8172fd1c85c45a4bffdf52d9ccb3f511c4b0c3ae38241",
}
"""Sabit revizyondaki dosyaların sha256'ları; uyuşmayan dosya yüklenmez."""

SEED = 0
"""Sabit tohum: aynı metin her seferinde aynı sesi versin."""

SPEED_MIN = 0.25
SPEED_MAX = 4.0
"""EMA'nın kabul ettiği hız aralığı."""


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

APOSTROPHES = "'\u2019\u2018\u02bc\u00b4`"
"""ASCII kesme ve `ema_lightning/frontend.py`'nin `TYPOGRAPHY` tablosunda ona çevrilen varyantlar: ’ ‘ ʼ ´ `."""

_APOSTROPHE_RUN = re.compile(f"[{re.escape(APOSTROPHES)}]")
_SPACE_RUN = re.compile(r"[ \t]{2,}")


def prepare_text(text: str) -> str:
    """EMA'ya gidecek metinden kesme işaretlerini çıkarır.

    EMA'nın metin düzenleyicisi (normalizer-tr, `POLICY = "fallback"`) harf harf
    okuduğu ifadelerde kesmeyi sesli okuyor: `EMA'nın` → "e me a kesme ne ı ne",
    `%20'si` → "yüzde yirmi kesme si". Her kesme boşlukla değiştirilir, art arda
    gelen boşluklar teke iner. Bilinen bedel: `2026'da` gibi sayılarda ek ayrı
    okunur ("iki bin yirmi altı da"). Mustafa dinleyerek karar verdi: seçici bir
    yöntem değil, düz değiştirme. Yalnızca EMA yolunda uygulanır; edge ve Piper
    metni olduğu gibi alır.
    """
    return _SPACE_RUN.sub(" ", _APOSTROPHE_RUN.sub(" ", text))


def check_version(installed: str | None) -> None:
    """Kurulu ema-lightning sürümünü denetler; 1.0.1 dışını reddeder."""
    if installed is None:
        raise SetupError("missing_package", "ema-lightning is not installed")
    if installed != REQUIRED_VERSION:
        raise SetupError(
            "wrong_version",
            f"ema-lightning {installed} installed, {REQUIRED_VERSION} required",
            installed=installed,
        )


def installed_version(distribution: str = "ema-lightning") -> str | None:
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


Downloader = Callable[..., str]
"""`hf_hub_download` imzası: (repo_id, filename, *, revision) → yerel yol."""


def fetch_model_files(download: Downloader) -> dict[str, Path]:
    """Model dosyalarını sabit revizyondan alır ve her birini doğrular.

    İlk kullanımda ağ gerekir; sonrasında `hf_hub_download` commit hash'i
    verilen dosyayı ağa çıkmadan önbellekten döner.
    """
    files: dict[str, Path] = {}
    for name in CHECKSUMS:
        try:
            local = Path(download(REPO_ID, name, revision=REVISION))
        except Exception as exc:  # ağ, önbellek ve HF hataları çeşitlidir
            raise SetupError(
                "download_failed", f"{name}: {type(exc).__name__}: {exc}"
            ) from exc
        verify_checksum(local, name)
        files[name] = local
    return files


def speed_from_rate(rate: float) -> float:
    """Pakize'nin `rate` çarpanını EMA'nın `speed` değerine çevirir.

    İkisi de "1'den büyük = daha hızlı" demek; değer olduğu gibi geçer.
    Aralık dışı değer sessizce kırpılmaz, hata verir: kullanıcı `rate = 5`
    yazdıysa sesin 4'te kaldığını fark etmeli (repo ilkesi: yazım hatası
    erken söylenir).
    """
    if not (SPEED_MIN <= rate <= SPEED_MAX):
        raise ValueError(
            f"rate {rate} is outside EMA's range {SPEED_MIN}-{SPEED_MAX}"
        )
    return float(rate)


# --- güvenli yükleme ---------------------------------------------------------


def safe_load_model(ema_pt: Path, decoder_pt: Path):
    """EMA modelini `torch.load(weights_only=True)` ile yükler.

    ema_lightning'in `load_acoustic` ve `load_decoder` fonksiyonları
    `weights_only=False` verir; yükleme süresince `torch.load` öyle bir
    sarmalayıcıyla değiştirilir ki anahtar ne verilirse verilsin True olur.
    `ema_lightning.model` ve `.decoder` modülleri aynı torch nesnesini paylaşır;
    yine de referans uygulamadaki gibi ikisinin de üzerinden yazılır.
    """
    import torch
    from ema_lightning import decoder as decoder_module
    from ema_lightning import model as model_module
    from ema_lightning.api import EMA
    from ema_lightning.frontend import Frontend

    original_load = torch.load

    @functools.wraps(original_load)
    def weights_only_load(*args, **kwargs):
        kwargs["weights_only"] = True
        return original_load(*args, **kwargs)

    torch.load = weights_only_load
    decoder_module.torch.load = weights_only_load
    model_module.torch.load = weights_only_load
    try:
        device = torch.device("cpu")
        model = model_module.load_acoustic(str(ema_pt), device)
        decoder = decoder_module.load_decoder(str(decoder_pt), device)
    finally:
        torch.load = original_load
        decoder_module.torch.load = original_load
        model_module.torch.load = original_load

    return EMA._from_parts(model, decoder, Frontend(model.vocab), device)


def prepare_model():
    """Sürümü denetler, dosyaları indirip doğrular, modeli güvenli yükler."""
    check_version(installed_version())
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SetupError("missing_package", f"{exc}") from exc

    files = fetch_model_files(hf_hub_download)
    try:
        return safe_load_model(files["ema.pt"], files["decoder.pt"])
    except ImportError as exc:  # torch ya da numpy eksik kurulmuş
        raise SetupError("missing_package", f"{exc}") from exc
    except Exception as exc:
        raise SetupError("load_failed", f"{type(exc).__name__}: {exc}") from exc


# --- sentez ------------------------------------------------------------------


def synthesize(tts: Any, request: dict[str, Any]) -> None:
    """Tek bir isteği seslendirip WAV olarak yazar."""
    speed = speed_from_rate(float(request.get("speed", 1.0)))
    volume = float(request.get("volume", 1.0))
    result = tts.say(request["text"], speed=speed, seed=SEED, sample_rate=SAMPLE_RATE)
    sample_rate = int(getattr(result, "sample_rate", SAMPLE_RATE))
    pcm = render_pcm(result.audio, volume, sample_rate)
    write_wav(Path(request["out"]), pcm, sample_rate)


def claim_stdout() -> TextIO:
    """Protokol için gerçek stdout'u ayırır; sonrasında stdout stderr'e akar.

    Hem `sys.stdout` hem de 1 numaralı dosya tanıtıcısı yönlendirilir: C
    tarafından yazan kütüphaneler Python nesnesini değil tanıtıcıyı kullanır.

    stderr UTF-8'e alınır: Windows'ta akış yerel kod sayfasıyla (cp1252)
    açılır, Pakize ise kuyruğu UTF-8 okur — Türkçe karakterler bozulurdu.
    `-I` bayrağı PYTHONIOENCODING'i yok saydığı için kodlama burada sabitlenir.
    Protokol kanalı zaten UTF-8 ve JSON satırları `ensure_ascii` ile ASCII'dir.
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
