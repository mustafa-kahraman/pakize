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
        sonuc: list[str] = []
        for batch in _batch(lines, MAX_REQUEST_CHARS):
            sonuc.extend(self._translate_batch(batch))
        return sonuc

    def _translate_batch(self, batch: list[str]) -> list[str]:
        """Bir grup satırı tek istekte çevirir.

        Uç satır sayısını değiştirirse (bazı metinlerde olabiliyor) satırlar
        tek tek çevrilir; sıranın bozulması, yavaşlamaktan daha kötüdür.
        """
        if not batch:
            return []
        if len(batch) == 1:
            return [self._request(batch[0])]

        cevrilen = self._request("\n".join(batch))
        satirlar = cevrilen.split("\n")
        if len(satirlar) == len(batch):
            return satirlar
        return [self._request(satir) for satir in batch]

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
            parcalar = data[0]
            self.detected = data[2] if len(data) > 2 else None
            return "".join(parca[0] for parca in parcalar if parca and parca[0])
        except (IndexError, KeyError, TypeError) as exc:
            raise TranslationError(
                _("Çeviri yanıtı anlaşılamadı: {error}").format(error=exc)
            ) from exc

    def _fetch(self, request: urllib.request.Request):
        """İsteği gönderir; hız sınırında artan gecikmeyle tekrar dener."""
        son_hata: Exception | None = None

        for deneme in range(MAX_ATTEMPTS):
            if self.pause_seconds and deneme == 0:
                time.sleep(self.pause_seconds)
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                son_hata = exc
                if exc.code not in (429, 503):
                    raise TranslationError(
                        _("Çeviri servisi hata verdi (HTTP {code})").format(
                            code=exc.code
                        )
                    ) from exc
                time.sleep(RETRY_BASE_SECONDS * (2**deneme))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                son_hata = exc
                time.sleep(RETRY_BASE_SECONDS * (2**deneme))

        raise TranslationError(
            _(
                "Çeviri servisine ulaşılamadı. Ücretsiz uç geçici olarak "
                "engellemiş olabilir; biraz sonra tekrar dene. ({error})"
            ).format(error=son_hata)
        )


def translate_segments(
    segments: list[Segment], translator: GoogleTranslator
) -> list[Segment]:
    """Segmentlerin metnini çevirir; kod ve tablolara dokunmaz.

    Kaynak dil zaten hedef dille aynıysa metin olduğu gibi bırakılır — kendi
    dilinde yazılmış bir metni gidip geri çevirmenin anlamı yok.
    """
    hedefler = [
        (index, segment)
        for index, segment in enumerate(segments)
        if segment.type in TRANSLATABLE and segment.text.strip()
    ]
    if not hedefler:
        return segments

    # Satır sayısının korunabilmesi için her segment tek satıra indirgenir;
    # seslendirmede satır sonlarının zaten bir karşılığı yok.
    satirlar = [" ".join(segment.text.split()) for _index, segment in hedefler]
    cevrilen = translator.translate_lines(satirlar)

    if translator.detected and translator.detected == translator.target:
        return segments

    sonuc = list(segments)
    for (index, segment), yeni_metin in zip(hedefler, cevrilen):
        sonuc[index] = replace(segment, text=yeni_metin)
    return sonuc


def _batch(lines: Sequence[str], max_chars: int) -> list[list[str]]:
    """Satırları, karakter sınırını aşmayan gruplara ayırır."""
    gruplar: list[list[str]] = []
    tampon: list[str] = []
    uzunluk = 0

    for line in lines:
        # +1: satırları birleştirirken araya girecek satır sonu.
        if tampon and uzunluk + len(line) + 1 > max_chars:
            gruplar.append(tampon)
            tampon, uzunluk = [], 0
        tampon.append(line)
        uzunluk += len(line) + 1

    if tampon:
        gruplar.append(tampon)
    return gruplar
