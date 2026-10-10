"""İşçi betiklerinin ortak ses yardımcıları: normalizasyon, parça sonu, WAV.

Bu dosya da `pakize`'yi İTHAL ETMEZ: işçi betikleri (`ema_worker.py`,
`antalia_worker.py`) ayrı Python ortamlarında, `-I` ile çalışır ve orada
`pakize` yoktur. Betikler kendi dizinlerini `sys.path`'e ekleyip bu modülü
doğrudan adıyla ithal eder. Modül düzeyinde yalnızca standart kütüphane
kullanılır; numpy varsa `render_pcm` onu fonksiyon içinde ithal eder.

Kurallar tek yerde durur: tepe hedefi, sönüm süresi ve kuyruk sessizliği
buradaki sabitlerdir; saf Python ve numpy yolları yalnızca uygular.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any, Iterable, Sequence

SAMPLE_RATE = 48000
"""Çıktı örnekleme hızı (Hz). Piper'la aynı: 16 bit, mono WAV."""

TARGET_PEAK = 0.95
"""Normalizasyon hedefi: her parçanın tepe genliği (volume = 1.0 iken)."""

FADE_OUT_SECONDS = 0.015
TAIL_SILENCE_SECONDS = 0.85
"""Parça sonu: kısa bir sönüm, ardından sessizlik.

EMA parçayı son kelimenin hemen ardından, düzey hâlâ sıfır değilken bitiriyor
(ölçüm: son 50 ms'de 0.0005–0.0075); 15 ms'lik kosinüs sönümü sesi sıfıra
indirir.

Sessizlik süresi dinleme testiyle seçildi. Akıcı modda her parça ayrı bir
ffplay ile çalınır ve ffplay parça bitince ses aygıtını kapatır; cızırtı
modelden ya da dosyadan değil, aygıt kapanırken sesin hâlâ sürmesinden
çıkıyor. Aynı dosyada: sessizlik yok → cızırtı var; 250 ms → azaldı ama var;
~850 ms (edge dosyalarının sonundaki kuyruk kadar, ölçülen 840–876 ms) →
cızırtı yok. 48 kHz'de 0.85 sn tam 40800 örnek eder.
"""


def gain_for(peak: float, volume: float) -> float:
    """Tepe `peak` olan sesi `TARGET_PEAK × volume`'a getiren çarpan.

    Sessiz parçada (tepe 0) çarpan 0'dır: sıfıra bölme olmaz, ses sessiz kalır.
    """
    if peak <= 0:
        return 0.0
    return TARGET_PEAK / peak * volume


def normalize(samples: Sequence[float], volume: float) -> list[float]:
    """Saf Python normalizasyon: tepe → 0.95 × volume, sonra [-1, 1]'e kırpma."""
    peak = max((abs(sample) for sample in samples), default=0.0)
    gain = gain_for(peak, volume)
    return [min(1.0, max(-1.0, sample * gain)) for sample in samples]


def fade_out_gains(length: int, sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Parçanın son örnekleri için sönüm çarpanları (kosinüs, 1'den tam 0'a).

    Parça sönüm süresinden kısaysa çarpan sayısı parça uzunluğuna iner; boş
    parçada liste boştur. Son örnek her zaman 0 ile çarpılır.
    """
    count = min(int(round(FADE_OUT_SECONDS * sample_rate)), length)
    return [0.5 * (1.0 + math.cos(math.pi * (i + 1) / count)) for i in range(count)]


def tail_silence_count(sample_rate: int = SAMPLE_RATE) -> int:
    """Parça sonuna eklenecek sıfır örnek sayısı."""
    return int(round(TAIL_SILENCE_SECONDS * sample_rate))


def shape_tail(samples: Sequence[float], sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Saf Python: sönümü uygular, sessizliği ekler. Normalizasyondan sonra çağrılır."""
    gains = fade_out_gains(len(samples), sample_rate)
    head = list(samples[: len(samples) - len(gains)])
    tail = [sample * gain for sample, gain in zip(samples[len(samples) - len(gains) :], gains)]
    return head + tail + [0.0] * tail_silence_count(sample_rate)


def to_pcm16(samples: Iterable[float]) -> bytes:
    """[-1, 1] aralığındaki örnekleri 16 bit işaretli PCM'e çevirir."""
    values = [int(round(min(1.0, max(-1.0, sample)) * 32767)) for sample in samples]
    return struct.pack(f"<{len(values)}h", *values)


def write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    """Mono, 16 bit WAV dosyası yazar."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def render_pcm(audio: Any, volume: float, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Modelin ürettiği float sesi normalize edip sonunu biçimler, 16 bit PCM'e çevirir.

    numpy varsa (gerçek işçide her zaman var) dizi işlemleriyle; yoksa saf
    Python ile. İki yol da kazancı `gain_for`, sönümü `fade_out_gains`,
    sessizliği `tail_silence_count` üzerinden alır: kural tek yerde durur,
    yollar yalnızca uygular.
    """
    if hasattr(audio, "detach"):  # torch tensörü
        audio = audio.detach().cpu().numpy()
    try:
        import numpy as np
    except ImportError:
        return to_pcm16(shape_tail(normalize(list(audio), volume), sample_rate))

    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    peak = float(np.abs(array).max()) if array.size else 0.0
    scaled = np.clip(array * gain_for(peak, volume), -1.0, 1.0)

    gains = fade_out_gains(int(scaled.size), sample_rate)
    split = int(scaled.size) - len(gains)
    shaped = np.concatenate(
        [
            scaled[:split],
            scaled[split:] * np.asarray(gains, dtype=np.float32),
            np.zeros(tail_silence_count(sample_rate), dtype=np.float32),
        ]
    )
    return (shaped * 32767).round().astype("<i2").tobytes()
