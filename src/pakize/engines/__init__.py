"""TTS motor adaptörleri.

Boru hattı yalnızca `TtsEngine` arayüzünü tanır; hangi motorun kullanıldığı
config'ten gelir. Yeni bir motor eklemek `_REGISTRY`'ye bir satır eklemektir.
"""

from __future__ import annotations

from ..config import Config
from ..i18n import _
from .base import EngineError, EngineUnavailable, TtsEngine
from .edge import EdgeEngine
from .piper import PiperEngine

_REGISTRY: dict[str, type[TtsEngine]] = {
    EdgeEngine.name: EdgeEngine,
    PiperEngine.name: PiperEngine,
}


def create_engine(name: str, config: Config) -> TtsEngine:
    """Ada göre motor örneği üretir."""
    engine_class = _REGISTRY.get(name)
    if engine_class is None:
        known = ", ".join(sorted(_REGISTRY))
        raise EngineError(
            _("Bilinmeyen motor: {name!r} (tanınanlar: {known})").format(
                name=name, known=known
            )
        )
    return engine_class(config)


def available_engines() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "TtsEngine",
    "EngineError",
    "EngineUnavailable",
    "EdgeEngine",
    "PiperEngine",
    "create_engine",
    "available_engines",
]
