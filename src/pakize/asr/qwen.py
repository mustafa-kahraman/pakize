"""Qwen3-ASR ile konuşmayı metne çevirme.

Model llama.cpp'nin sunucusunda çalışır; Pakize ona HTTP ile sorar. Piper'da
olduğu gibi ağır makine öğrenmesi bağımlılıkları Pakize'nin içine girmez ve
model hangi yolla kurulmuş olursa olsun aynı şekilde kullanılır.

Bağlam metni **sistem mesajına** konur. Model bunu arka plan bilgisi sayıp
tanımayı oraya yaslar: paragrafta "seslendirmede edge-tts var" yazıyorsa,
konuşmacı "ecdi tiitiies" dediğinde "edge-tts" yazar. Sunucunun deşifre ucuna
(`/v1/audio/transcriptions`) verilen istem ise metni çıktının başına kopyalar;
o yüzden sohbet ucu kullanılır.

Sohbet ucu da bağışık değil: kısa ya da belirsiz bir seste model bazen sesi
yazacağına bağlamı olduğu gibi kopyalıyor (yaşandı: "merhaba Pakize" dendi,
paragrafın tamamı döndü). Bu yakalanır ve aynı ses bağlamsız yeniden sorulur.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import ClassVar

from ..i18n import _
from .base import AsrEngine, AsrError, AsrUnavailable
from .http import post_json

ENDPOINT = "/v1/chat/completions"

TEXT_MARKER = "<asr_text>"
"""Model metni bu işaretin ardında verir; öncesi dilin tespitidir."""

_FORMATS = {".wav": "wav", ".mp3": "mp3"}
"""Tanınan ses uzantıları ve sunucuya bildirilen biçim adları."""

ECHO_MIN_CHARS = 20
"""Bağlamın bu uzunlukta bir cümlesi çıktıda aynen geçiyorsa kopyalama sayılır.

Konuşmacının bağlamdaki bir cümleyi kelimesi kelimesine söylemesi olası değil;
kısa parçalar ("Pakize" gibi terimler) ise tam da bağlamın işi, sayılmaz.
"""


class QwenEngine(AsrEngine):
    name: ClassVar[str] = "qwen"

    def ensure_available(self) -> None:
        if not self.config.asr_server_url:
            raise AsrUnavailable(
                _(
                    "Deşifre için sunucu adresi gerekli. Config'e ekle:\n"
                    '  asr_server_url = "http://127.0.0.1:8099"'
                )
            )

    def _recognize(self, audio: Path) -> str:
        self.ensure_available()
        context = (self.config.asr_context or "").strip()
        text = self._ask(audio, context)
        if context and _echoes_context(text, context):
            # Model sesi yazacağına bağlamı kopyaladı; bağlamsız sorulur.
            # Terim yanlılığı bu seferlik kaybolur, konuşma kaybolmaz.
            text = self._ask(audio, "")
        return text

    def _ask(self, audio: Path, context: str) -> str:
        payload = self._payload(audio, context)
        response = post_json(self._url(), payload, self.config.asr_timeout)
        return _extract_text(response)

    def _url(self) -> str:
        return self.config.asr_server_url.rstrip("/") + ENDPOINT

    def _payload(self, audio: Path, context: str) -> dict:
        """Sunucuya gidecek istek gövdesini kurar."""
        messages: list[dict] = []
        if context:
            messages.append({"role": "system", "content": context})

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": _encode(audio),
                            "format": _format(audio),
                        },
                    }
                ],
            }
        )
        # Deşifre yaratıcılık değil: aynı ses her seferinde aynı metni vermeli.
        return {"messages": messages, "temperature": 0}


def _echoes_context(text: str, context: str) -> bool:
    """Çıktı, sesin yazısı değil de bağlamın kopyası mı?"""
    for sentence in re.split(r"[.!?;\n]+", context):
        sentence = sentence.strip()
        if len(sentence) >= ECHO_MIN_CHARS and sentence in text:
            return True
    return False


def _format(audio: Path) -> str:
    """Uzantıdan sunucuya bildirilecek biçim adını bulur."""
    audio_format = _FORMATS.get(audio.suffix.lower())
    if audio_format is None:
        raise AsrError(
            _("Tanınmayan ses biçimi: {suffix} (tanınanlar: {known})").format(
                suffix=audio.suffix or audio.name, known=", ".join(sorted(_FORMATS))
            )
        )
    return audio_format


def _encode(audio: Path) -> str:
    try:
        return base64.b64encode(audio.read_bytes()).decode("ascii")
    except OSError as exc:
        raise AsrError(
            _("Ses dosyası okunamadı: {path} ({reason})").format(
                path=audio, reason=exc
            )
        ) from exc


def _extract_text(response: dict) -> str:
    """Sunucu yanıtından metni çıkarır ve dil önekini ayıklar.

    Yanıtın biçimi beklenenden saparsa `KeyError`/`IndexError` dışarı sızmaz;
    kullanıcı anlaşılır bir hata görür.
    """
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AsrError(_("Deşifre sunucusu beklenmedik bir yanıt döndürdü.")) from exc

    if not isinstance(content, str):
        raise AsrError(_("Deşifre sunucusu beklenmedik bir yanıt döndürdü."))

    # `_` adı i18n'in çeviri işlevine ait; buradaki değerler ona dokunmadan alınır.
    marker_at = content.find(TEXT_MARKER)
    if marker_at < 0:
        return content.strip()
    return content[marker_at + len(TEXT_MARKER) :].strip()
