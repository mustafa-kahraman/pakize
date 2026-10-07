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

    Bölme, sıralama ve birleştirme boru hattının işidir; motor yalnızca tek bir
    parçayı seslendirir. Bir motor nesnesi tek bir seslendirme işi boyunca
    yaşar ve `synthesize` çağrıları arasında kaynak tutabilir (EMA'nın yüklü
    modelle bekleyen işçi süreci gibi). İş bitince boru hattı `aclose` ile bu
    kaynakları bıraktırır; durumsuz motorlar (edge, piper) varsayılan boş
    gövdeyi kullanır.
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

    async def aclose(self) -> None:
        """İş bitince motorun tuttuğu kaynakları bırakır.

        Boru hattı bunu her durumda — başarı, hata, iptal — `finally` içinde
        çağırır. Kaynak tutmayan motor için yapacak bir şey yoktur.
        """
        return None
