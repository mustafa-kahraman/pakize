"""Deşifre çıktısına uygulanan düzeltme tablosu.

Bağlam modele yol gösterir ama garanti vermez; `uv`, `EPUB` gibi kısa ya da
tuhaf okunan terimler en iyi bağlamda bile yanlış yazılabiliyor. Bu tablo o
kalan hataları modelsiz ve öngörülebilir biçimde düzeltir.
"""

from __future__ import annotations

import re


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """`replacements`'taki yanlış yazımları doğrularıyla değiştirir.

    Yalnız bütün kelime eşleşir: "Apab" düzeltmesi "Apabey"e dokunmamalı.
    Büyük-küçük harf ayrı sayılır; Türkçede "I/ı" ile "İ/i" dönüşümü dile
    bağlı olduğundan, harf duyarsız eşleşme kimi zaman şaşırtıcı sonuç verirdi.

    Tek geçişte yapılır: bir düzeltmenin çıktısı başka bir düzeltmenin
    girdisi olmaz, tablonun sırası sonucu değiştirmez. Örtüşen anahtarlarda
    uzun olan kazanır ("Ecdi TTS", "TTS"den önce denenir).
    """
    if not replacements:
        return text

    keys = sorted(replacements, key=len, reverse=True)
    alternation = "|".join(re.escape(key) for key in keys)
    pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")
    return pattern.sub(lambda match: replacements[match.group(0)], text)
