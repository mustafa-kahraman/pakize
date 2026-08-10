"""Piper ile tamamen çevrimdışı seslendirme.

edge-tts internete ve Microsoft'un resmî olmayan bir ucuna bağımlıdır. Piper
ise yerelde çalışır: ağ yoksa ya da servis bozulursa devreye girer. Karşılığında
Türkçe ses kalitesi edge-tts'in bir tık altındadır.

Piper harici bir çalıştırılabilirdir; Python paketi olarak gömmek yerine dışarıdan
çağırırız. Böylece Pakize'nin çekirdeği ağır makine öğrenmesi bağımlılıkları
taşımaz ve hangi yolla kurulmuş olursa olsun aynı şekilde kullanılır.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import ClassVar

from .base import EngineError, EngineUnavailable, TtsEngine

DEFAULT_BINARY = "piper"


class PiperEngine(TtsEngine):
    name: ClassVar[str] = "piper"
    output_suffix: ClassVar[str] = ".wav"

    def ensure_available(self) -> None:
        self._binary()
        model = self.config.piper_model
        if model is None:
            raise EngineUnavailable(
                "piper motoru için ses modeli gerekli. Config'e ekle:\n"
                '  piper_model = "/yol/tr_TR-dfki-medium.onnx"'
            )
        if not model.is_file():
            raise EngineUnavailable(f"Piper ses modeli bulunamadı: {model}")

    async def synthesize(self, text: str, destination: Path) -> None:
        command = [
            self._binary(),
            "--model",
            str(self.config.piper_model),
            "--output-file",
            str(destination),
            "--length-scale",
            f"{self._length_scale():.4f}",
            "--volume",
            f"{self.config.volume:.4f}",
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate(text.encode("utf-8"))

        if process.returncode != 0:
            detay = stderr.decode(errors="replace").strip()
            raise EngineError(f"piper seslendirme başarısız: {detay}")

        if not destination.is_file() or destination.stat().st_size == 0:
            raise EngineError("piper boş ses dosyası üretti")

    def _binary(self) -> str:
        """Piper çalıştırılabilirinin yolu; bulunamazsa kurulum ipucu verir."""
        configured = self.config.piper_binary
        if configured is not None:
            if not configured.is_file():
                raise EngineUnavailable(f"piper çalıştırılabiliri yok: {configured}")
            return str(configured)

        found = shutil.which(DEFAULT_BINARY)
        if found is None:
            raise EngineUnavailable(
                "piper bulunamadı. Kurmak için: uv tool install piper-tts\n"
                "Kuruluysa yolunu config'e yaz: piper_binary = \"/yol/piper\""
            )
        return found

    def _length_scale(self) -> float:
        """Hız çarpanını Piper'ın beklediği fonem uzunluğuna çevirir.

        Piper hızı süre üzerinden ifade eder: uzunluk arttıkça konuşma yavaşlar.
        Bu yüzden hız çarpanının tersini veririz — 1.15 hız, 0.87 uzunluk.
        """
        rate = self.config.rate
        if rate <= 0:
            raise EngineError("rate pozitif olmalı")
        return 1.0 / rate
