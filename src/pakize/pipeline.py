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
from typing import Callable

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
) -> SpeechResult:
    """Metni sese çevirip `destination` yoluna yazar (eşzamanlı sarmalayıcı)."""
    return asyncio.run(synthesize_async(text, destination, config, progress))


async def synthesize_async(
    text: str,
    destination: Path,
    config: Config,
    progress: ProgressCallback | None = None,
) -> SpeechResult:
    plan = plan_speech(text, config)
    if not plan.chunks:
        raise EngineError(
            "Seslendirilecek içerik kalmadı — metin tamamen atlanan "
            "segmentlerden oluşuyor olabilir"
        )

    last_error: EngineError | None = None
    for engine_name in _engine_order(config):
        try:
            await _render_with_engine(engine_name, plan, destination, config, progress)
        except EngineError as exc:
            last_error = exc
            continue
        return SpeechResult(output=destination, plan=plan, engine=engine_name)

    assert last_error is not None
    raise last_error


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
) -> None:
    """Tüm parçaları tek bir motorla seslendirip birleştirir."""
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

        parts = await asyncio.gather(*(render(chunk) for chunk in plan.chunks))
        concat(list(parts), destination)


__all__ = [
    "Plan",
    "SpeechResult",
    "plan_speech",
    "synthesize",
    "synthesize_async",
    "EngineError",
    "EngineUnavailable",
]
