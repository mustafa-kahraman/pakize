"""Microsoft Edge "Read Aloud" servisini kullanan motor (edge-tts).

Ücretsiz ve Türkçe kalitesi yüksek; karşılığında internet bağlantısı ister ve
resmî olarak desteklenen bir API değildir. Bu yüzden hatalar `EngineError`
olarak sarılır ve boru hattı gerektiğinde yedek motora düşebilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import edge_tts

from .base import EngineError, EngineUnavailable, TtsEngine


class EdgeEngine(TtsEngine):
    name: ClassVar[str] = "edge"

    def ensure_available(self) -> None:
        if not self.config.voice:
            raise EngineUnavailable("edge motoru için bir ses adı gerekli")

    async def synthesize(self, text: str, destination: Path) -> None:
        # Kurucu da doğrulama yapıp hata fırlatıyor (geçersiz ses adı gibi);
        # bu yüzden nesne oluşturma da sarmalın içinde olmalı. Aksi hâlde ham
        # traceback dökülür ve yedek motora hiç geçilmez.
        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self.config.voice,
                rate=self.config.rate_percent(),
                volume=self.config.volume_percent(),
                pitch=self.config.pitch_spec(),
            )
            await communicate.save(str(destination))
        except Exception as exc:  # edge-tts ağ/protokol hatalarını çeşitlendirir
            raise EngineError(f"edge-tts seslendirme başarısız: {exc}") from exc

        if not destination.is_file() or destination.stat().st_size == 0:
            raise EngineError(
                "edge-tts boş ses dosyası üretti — metin okunabilir içerik "
                "içermiyor olabilir"
            )

    @staticmethod
    async def list_voices(language: str | None = None) -> list[dict]:
        """Servisin sunduğu sesleri döner; `language` verilirse ön ekle filtreler."""
        voices = await edge_tts.list_voices()
        if language is None:
            return voices
        prefix = language.lower()
        return [v for v in voices if v["ShortName"].lower().startswith(prefix)]
