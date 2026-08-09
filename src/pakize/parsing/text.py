"""Türkçe seslendirme için metin normalizasyonu.

Politika kararlarından bağımsız, dile özgü düzeltmeler burada yaşar. Şu an tek
konu ondalık ayracı: Türkçe'de ondalık ayracı virgüldür, nokta ise binlik
ayracıdır. `1.15` yazımı TTS motoruna Türkçe kurallarıyla gittiğinde yanlış
okunur; `1,15` doğru okunur.
"""

from __future__ import annotations

import re

# Yalnızca tek noktalı, iki gruplu sayılar dönüştürülür. Öncesinde/sonrasında
# başka bir nokta veya rakam varsa (1.2.3, 192.168.1.1, 09.08.2026) dokunulmaz;
# sonrasında harf varsa (3.10rc1) da dokunulmaz.
_DECIMAL_RE = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.]|\w)")


def normalize_decimals(text: str) -> str:
    """Ondalık sayılardaki noktayı virgüle çevirir.

    Sürüm numaraları da bu kalıba uyar (`Python 3.10` → `Python 3,10`). İkisini
    metne bakarak ayırmak mümkün olmadığı için davranış config'ten kapatılabilir.
    """
    return _DECIMAL_RE.sub(r"\1,\2", text)
