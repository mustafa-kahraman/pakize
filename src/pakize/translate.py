"""Metni seslendirmeden önce çeviren katman.

Çeviri, ayrıştırmadan sonra ve politika uygulanmadan önce çalışır. Sırası
önemlidir:

* Ayrıştırmadan **sonra** olmalı ki kod blokları ve tablolar çeviriye hiç
  girmesin — hem gereksiz hem de kodu bozar.
* Politikadan **önce** olmalı ki "Burada 12 satırlık bir Python kod bloğu var"
  gibi bizim ürettiğimiz Türkçe anonslar tekrar çevrilmesin.

Google'ın ücretsiz ucu resmî bir API değildir: kota belirsizdir ve çok sayıda
istekte geçici olarak engellenebilir. Bu yüzden istekler seri gönderilir,
aralarında kısa bir bekleme olur ve 429 yanıtında artan gecikmeyle tekrar
denenir.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Sequence

from .i18n import _
from .models import Segment, SegmentType

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
USER_AGENT = "Mozilla/5.0"

MAX_REQUEST_CHARS = 4000
"""Tek istekte gönderilecek azami karakter. Ucun sınırı ~5000."""

TRANSLATABLE = frozenset(
    {
        SegmentType.PROSE,
        SegmentType.HEADING,
        SegmentType.LIST_ITEM,
        SegmentType.QUOTE,
    }
)
"""Çevrilen segment tipleri. Kod, tablo ve bağlantılar dışarıda kalır."""

MAX_ATTEMPTS = 4
RETRY_BASE_SECONDS = 2.0


class TranslationError(RuntimeError):
    """Çeviri yapılamadığında oluşan, kullanıcıya gösterilebilir hata."""


@dataclass
class GoogleTranslator:
    """Google'ın ücretsiz çeviri ucunu kullanan çevirmen.

    Satırlar toplu gönderilir: uç satır sonlarını koruduğu için tek istekte
    çok sayıda segment çevrilebilir. Bir kitapta bu, binlerce istek yerine
    yüzlerce istek demektir.
    """

    target: str
    source: str = "auto"
    pause_seconds: float = 0.2
    """İstekler arası bekleme — ücretsiz uca yüklenmemek için."""

    detected: str | None = None
    """Son istekte tespit edilen kaynak dil."""

    def translate_lines(self, lines: Sequence[str]) -> list[str]:
        """Satırları sırayı ve sayıyı koruyarak çevirir."""
        result: list[str] = []
        for batch in _batch(lines, MAX_REQUEST_CHARS):
            result.extend(self._translate_batch(batch))
        return result

    def _translate_batch(self, batch: list[str]) -> list[str]:
        """Bir grup satırı tek istekte çevirir.

        Uç satır sayısını değiştirirse (bazı metinlerde olabiliyor) satırlar
        tek tek çevrilir; sıranın bozulması, yavaşlamaktan daha kötüdür.
        """
        if not batch:
            return []
        if len(batch) == 1:
            return [self._request(batch[0])]

        translated = self._request("\n".join(batch))
        lines = translated.split("\n")
        if len(lines) == len(batch):
            return lines
        return [self._request(line) for line in batch]

    def _request(self, text: str) -> str:
        """Tek bir metni çevirir; boş metinde ağa çıkmaz."""
        if not text.strip():
            return text

        params = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": self.source,
                "tl": self.target,
                "dt": "t",
                "q": text,
            }
        )
        request = urllib.request.Request(
            f"{ENDPOINT}?{params}", headers={"User-Agent": USER_AGENT}
        )

        data = self._fetch(request)
        try:
            pieces = data[0]
            self.detected = data[2] if len(data) > 2 else None
            return "".join(piece[0] for piece in pieces if piece and piece[0])
        except (IndexError, KeyError, TypeError) as exc:
            raise TranslationError(
                _("Çeviri yanıtı anlaşılamadı: {error}").format(error=exc)
            ) from exc

    def _fetch(self, request: urllib.request.Request):
        """İsteği gönderir; hız sınırında artan gecikmeyle tekrar dener."""
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            if self.pause_seconds and attempt == 0:
                time.sleep(self.pause_seconds)
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in (429, 503):
                    raise TranslationError(
                        _("Çeviri servisi hata verdi (HTTP {code})").format(
                            code=exc.code
                        )
                    ) from exc
                time.sleep(RETRY_BASE_SECONDS * (2**attempt))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(RETRY_BASE_SECONDS * (2**attempt))

        raise TranslationError(
            _(
                "Çeviri servisine ulaşılamadı. Ücretsiz uç geçici olarak "
                "engellemiş olabilir; biraz sonra tekrar dene. ({error})"
            ).format(error=last_error)
        )


def translate_segments(
    segments: list[Segment], translator: GoogleTranslator
) -> list[Segment]:
    """Segmentlerin metnini çevirir; kod ve tablolara dokunmaz.

    Kaynak dil zaten hedef dille aynıysa metin olduğu gibi bırakılır — kendi
    dilinde yazılmış bir metni gidip geri çevirmenin anlamı yok.
    """
    targets = [
        (index, segment)
        for index, segment in enumerate(segments)
        if segment.type in TRANSLATABLE and segment.text.strip()
    ]
    if not targets:
        return segments

    # Satır sayısının korunabilmesi için her segment tek satıra indirgenir;
    # seslendirmede satır sonlarının zaten bir karşılığı yok.
    lines = [" ".join(segment.text.split()) for _index, segment in targets]
    translated = translator.translate_lines(lines)

    if translator.detected and translator.detected == translator.target:
        return segments

    result = list(segments)
    for (index, segment), new_text in zip(targets, translated):
        result[index] = replace(segment, text=new_text)
    return result


def _batch(lines: Sequence[str], max_chars: int) -> list[list[str]]:
    """Satırları, karakter sınırını aşmayan gruplara ayırır."""
    groups: list[list[str]] = []
    buffer: list[str] = []
    length = 0

    for line in lines:
        # +1: satırları birleştirirken araya girecek satır sonu.
        if buffer and length + len(line) + 1 > max_chars:
            groups.append(buffer)
            buffer, length = [], 0
        buffer.append(line)
        length += len(line) + 1

    if buffer:
        groups.append(buffer)
    return groups
