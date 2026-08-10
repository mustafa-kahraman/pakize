"""Metinden ses dosyasına giden boru hattı — Pakize'nin tek giriş noktası.

CLI, pano kısayolu, transkript okuyucu ve web arayüzü hepsi buradaki
`synthesize` fonksiyonunu çağırır; iş mantığı başka hiçbir yerde tekrarlanmaz.

    metin → parse_segments → apply_policy → build_chunks → motor → concat
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Awaitable, Callable

from .audio import concat
from .chunking import build_chunks
from .config import Config
from .engines import EngineError, EngineUnavailable, create_engine
from .models import Chunk, SegmentType
from .parsing import apply_policy, parse_segments

MAX_CONCURRENT_REQUESTS = 4
"""Aynı anda kaç parçanın seslendirileceği.

Paralellik toplam süreyi belirgin düşürür; sınırı düşük tutmak ise ücretsiz
servisi zorlamamak ve hız sınırına takılmamak içindir.
"""

ProgressCallback = Callable[[int, int], None]
"""(tamamlanan, toplam) parça sayısıyla çağrılır."""

PartReadyCallback = Callable[[Path], Awaitable[None]]
"""Hazır olan her ses parçası için, **parça sırasına göre** beklenerek çağrılır.

Akıcı çalmayı bu geri çağrı sağlar; boru hattı ses çalmayı bilmez, yalnızca
sırayı garanti eder.
"""


@dataclass(frozen=True)
class Plan:
    """Seslendirme öncesi hazırlanan, henüz sese çevrilmemiş iş planı."""

    chunks: list[Chunk] = field(default_factory=list)
    skipped: dict[SegmentType, int] = field(default_factory=dict)

    @property
    def total_chars(self) -> int:
        return sum(len(chunk.text) for chunk in self.chunks)


@dataclass(frozen=True)
class SpeechResult:
    """Tamamlanmış bir seslendirme işinin sonucu."""

    output: Path
    plan: Plan
    engine: str
    """Sesi gerçekten üreten motorun adı (yedeğe düşülmüş olabilir)."""


def plan_speech(text: str, config: Config) -> Plan:
    """Metni ayrıştırıp seslendirilecek parçaları hesaplar; ses üretmez.

    Web arayüzünün önizlemesi ve CLI'ın `--dry-run` modu bunu kullanır.
    """
    segments = parse_segments(text)
    utterances, skipped = apply_policy(segments, config)
    chunks = build_chunks(utterances, config.max_chunk_chars)
    return Plan(chunks=chunks, skipped=skipped)


def synthesize(
    text: str,
    destination: Path,
    config: Config,
    progress: ProgressCallback | None = None,
    on_part_ready: PartReadyCallback | None = None,
) -> SpeechResult:
    """Metni sese çevirip `destination` yoluna yazar (eşzamanlı sarmalayıcı)."""
    return asyncio.run(
        synthesize_async(text, destination, config, progress, on_part_ready)
    )


async def synthesize_async(
    text: str,
    destination: Path,
    config: Config,
    progress: ProgressCallback | None = None,
    on_part_ready: PartReadyCallback | None = None,
) -> SpeechResult:
    plan = plan_speech(text, config)
    if not plan.chunks:
        raise EngineError(
            "Seslendirilecek içerik kalmadı — metin tamamen atlanan "
            "segmentlerden oluşuyor olabilir"
        )

    # Hepsi başarısız olursa birincil motorun hatası gösterilir: yedeğin
    # "kurulu değil" mesajı, asıl sorunun ne olduğunu gizlerdi.
    primary_error: EngineError | None = None
    for engine_name in _engine_order(config):
        try:
            await _render_with_engine(
                engine_name, plan, destination, config, progress, on_part_ready
            )
        except EngineError as exc:
            primary_error = primary_error or exc
            continue
        return SpeechResult(output=destination, plan=plan, engine=engine_name)

    assert primary_error is not None
    raise primary_error


def _engine_order(config: Config) -> list[str]:
    """Denenecek motorlar: önce birincil, sonra (varsa) yedek."""
    order = [config.engine]
    if config.fallback_engine and config.fallback_engine != config.engine:
        order.append(config.fallback_engine)
    return order


async def _render_with_engine(
    engine_name: str,
    plan: Plan,
    destination: Path,
    config: Config,
    progress: ProgressCallback | None,
    on_part_ready: PartReadyCallback | None,
) -> None:
    """Tüm parçaları tek bir motorla seslendirip birleştirir.

    Parçalar paralel üretilir; `on_part_ready` verilmişse üretim sürerken
    hazır olanlar sırayla tüketilir. Böylece uzun metinlerde ilk sese kadar
    beklenen süre, tüm metnin değil yalnızca ilk parçanın süresidir.
    """
    engine = create_engine(engine_name, replace(config, engine=engine_name))
    engine.ensure_available()

    with tempfile.TemporaryDirectory(prefix="pakize-") as workdir:
        root = Path(workdir)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        completed = 0

        async def render(chunk: Chunk) -> Path:
            nonlocal completed
            part = root / f"{chunk.index:05d}{engine.output_suffix}"
            async with semaphore:
                await engine.synthesize(chunk.text, part)
            completed += 1
            if progress is not None:
                progress(completed, len(plan.chunks))
            return part

        # Görevler burada başlar; aşağıdaki sıralı tüketim üretimi beklemez.
        tasks = [asyncio.create_task(render(chunk)) for chunk in plan.chunks]
        try:
            parts = await _collect(tasks, on_part_ready)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        concat(parts, destination)


async def _collect(
    tasks: list[asyncio.Task],
    on_part_ready: PartReadyCallback | None,
) -> list[Path]:
    """Parçaları sırayla toplar, her biri hazır oldukça geri çağrıyı bekler."""
    parts: list[Path] = []
    for task in tasks:
        part = await task
        parts.append(part)
        if on_part_ready is not None:
            await on_part_ready(part)
    return parts


__all__ = [
    "Plan",
    "SpeechResult",
    "plan_speech",
    "synthesize",
    "synthesize_async",
    "EngineError",
    "EngineUnavailable",
]
