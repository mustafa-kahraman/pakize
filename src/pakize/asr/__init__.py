"""Konuşmayı metne çeviren motor adaptörleri.

Çağıran yalnızca `AsrEngine` arayüzünü tanır; hangi motorun kullanıldığı
config'ten gelir. Yeni bir motor eklemek `_REGISTRY`'ye bir satır eklemektir.
"""

from __future__ import annotations

from ..config import Config
from ..i18n import _
from .base import AsrEngine, AsrError, AsrUnavailable
from .qwen import QwenEngine
from .server import asr_server, check_asr_setup

_REGISTRY: dict[str, type[AsrEngine]] = {
    QwenEngine.name: QwenEngine,
}


def create_asr_engine(name: str, config: Config) -> AsrEngine:
    """Ada göre motor örneği üretir."""
    engine_class = _REGISTRY.get(name)
    if engine_class is None:
        known = ", ".join(sorted(_REGISTRY))
        raise AsrError(
            _("Bilinmeyen deşifre motoru: {name!r} (tanınanlar: {known})").format(
                name=name, known=known
            )
        )
    return engine_class(config)


def available_asr_engines() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "AsrEngine",
    "AsrError",
    "AsrUnavailable",
    "QwenEngine",
    "asr_server",
    "check_asr_setup",
    "create_asr_engine",
    "available_asr_engines",
]
