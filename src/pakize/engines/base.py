"""TTS motorlarının uyması gereken sözleşme."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import ClassVar

from ..config import Config


class EngineError(RuntimeError):
    """Seslendirme sırasında oluşan, kullanıcıya gösterilebilir hata."""


class EngineUnavailable(EngineError):
    """Motor bu makinede/koşullarda kullanılamıyor (eksik kurulum, ağ yok...)."""


class TtsEngine(abc.ABC):
    """Metni ses dosyasına çeviren adaptör.

    Motorlar durumsuzdur: her `synthesize` çağrısı bağımsızdır. Bölme, sıralama
    ve birleştirme boru hattının işidir; motor yalnızca tek bir parçayı seslendirir.
    """

    name: ClassVar[str]
    """Config'te ve CLI'da kullanılan kısa ad."""

    output_suffix: ClassVar[str] = ".mp3"
    """Motorun ürettiği ses dosyası uzantısı."""

    def __init__(self, config: Config) -> None:
        self.config = config

    @abc.abstractmethod
    def ensure_available(self) -> None:
        """Motor kullanılabilir değilse `EngineUnavailable` fırlatır."""

    @abc.abstractmethod
    async def synthesize(self, text: str, destination: Path) -> None:
        """`text`'i seslendirip `destination` yoluna yazar."""
