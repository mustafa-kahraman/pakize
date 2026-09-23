"""Konuşmayı metne çeviren motorların uyması gereken sözleşme.

TTS tarafındaki `engines/base.py`'nin aynası: Pakize'nin iki yönü de aynı
biçimde takılıp çıkarılabilsin diye sözleşme, hata tipleri ve kayıt defteri
birebir aynı desende durur.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import ClassVar

from ..config import Config
from .replacements import apply_replacements


class AsrError(RuntimeError):
    """Deşifre sırasında oluşan, kullanıcıya gösterilebilir hata."""


class AsrUnavailable(AsrError):
    """Motor bu makinede/koşullarda kullanılamıyor (eksik ayar, sunucu yok...)."""


class AsrEngine(abc.ABC):
    """Ses dosyasını metne çeviren adaptör.

    Motorlar durumsuzdur: her `transcribe` çağrısı bağımsızdır. Kaydı almak,
    parçalamak ve metni bir yere koymak çağıranın işidir; motor yalnızca tek
    bir dosyayı metne çevirir.

    Motorlar `_recognize`'ı yazar; config'teki düzeltme tablosunu `transcribe`
    uygular. Böylece hangi motor seçilirse seçilsin ve metin nereye giderse
    gitsin (ekran, dosya, pano) düzeltme atlanamaz.
    """

    name: ClassVar[str]
    """Config'te ve CLI'da kullanılan kısa ad."""

    def __init__(self, config: Config) -> None:
        self.config = config

    @abc.abstractmethod
    def ensure_available(self) -> None:
        """Motor kullanılabilir değilse `AsrUnavailable` fırlatır."""

    def transcribe(self, audio: Path) -> str:
        """`audio` dosyasındaki konuşmayı metne çevirir ve düzeltir."""
        return apply_replacements(
            self._recognize(audio), self.config.asr_replacements
        )

    @abc.abstractmethod
    def _recognize(self, audio: Path) -> str:
        """Modelin ham çıktısını döner; düzeltme tablosu henüz uygulanmamış."""
