"""Seslendirilecek metin parçalarını TTS isteklerine böler.

Motorlar çok uzun metinlerde yavaşlar veya hata verir; bu yüzden metni sabit
bir karakter sınırına göre paketleriz. Kesme noktası **asla** karakter sayısı
değil, önce söyleyiş sonra cümle sınırıdır — böylece ses dosyaları cümle
ortasında bölünmez.
"""

from __future__ import annotations

import re

from .models import Chunk

# Cümle sonu: nokta/ünlem/soru/üç nokta + boşluk. Ondalıklı sayıları (1.15) ve
# kısaltmaları bölmemek için nokta sonrası küçük harf/rakam gelen durumlar
# cümle sonu sayılmaz.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+(?=[^\ta-zçğıöşü0-9])")
_SOFT_BREAK_RE = re.compile(r"(?<=[,;:])\s+")


def build_chunks(utterances: list[str], max_chars: int) -> list[Chunk]:
    """Söyleyişleri sırayı bozmadan `max_chars`'ı aşmayan parçalara paketler."""
    if max_chars <= 0:
        raise ValueError("max_chars pozitif olmalı")

    pieces: list[str] = []
    for utterance in utterances:
        pieces.extend(_fit(utterance, max_chars))

    chunks: list[Chunk] = []
    buffer = ""

    for piece in pieces:
        candidate = f"{buffer}\n{piece}" if buffer else piece
        if len(candidate) <= max_chars:
            buffer = candidate
            continue

        if buffer:
            chunks.append(Chunk(text=buffer, index=len(chunks)))
        buffer = piece

    if buffer:
        chunks.append(Chunk(text=buffer, index=len(chunks)))

    return chunks


def _fit(text: str, max_chars: int) -> list[str]:
    """Tek bir söyleyişi sınıra sığan parçalara böler.

    Sırasıyla cümle, ardından virgül/noktalı virgül, en son boşluk sınırı
    denenir; hiçbiri yetmezse metin ham olarak kesilir.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    for splitter in (_SENTENCE_END_RE, _SOFT_BREAK_RE):
        parts = _pack(splitter.split(text), max_chars, separator=" ")
        if all(len(part) <= max_chars for part in parts):
            return parts

    return _pack_words(text, max_chars)


def _pack(parts: list[str], max_chars: int, separator: str) -> list[str]:
    """Parçaları sırayı koruyarak sınıra kadar birleştirir."""
    packed: list[str] = []
    buffer = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        candidate = f"{buffer}{separator}{part}" if buffer else part
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            packed.append(buffer)
        buffer = part

    if buffer:
        packed.append(buffer)
    return packed


def _pack_words(text: str, max_chars: int) -> list[str]:
    """Son çare: kelime sınırında böler, tek kelime sığmıyorsa ham keser."""
    packed = _pack(text.split(" "), max_chars, separator=" ")

    result: list[str] = []
    for part in packed:
        while len(part) > max_chars:
            result.append(part[:max_chars])
            part = part[max_chars:]
        if part:
            result.append(part)
    return result
