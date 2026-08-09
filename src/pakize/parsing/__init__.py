"""Metni anlamsal segmentlere ayırma ve onlara politika uygulama katmanı."""

from .markdown import parse_segments
from .policy import apply_policy

__all__ = ["parse_segments", "apply_policy"]
