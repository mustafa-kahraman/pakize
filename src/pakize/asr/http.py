"""Deşifre sunucusuna yapılan JSON çağrısı.

İki sebeple ayrı bir modülde duruyor. Birincisi testler: ağa çıkmadan
yamalanabilecek tek bir yüzey kalsın. İkincisi bağımlılık: standart kütüphane
yetiyor, Pakize'nin bağımlılık listesi bu özellik için büyümesin.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..i18n import _
from .base import AsrError

_DETAIL_LIMIT = 200
"""Sunucunun hata gövdesinden mesaja alınacak azami karakter."""


def post_json(url: str, payload: dict, timeout: float) -> dict:
    """`payload`'ı JSON olarak POST eder, yanıtı sözlük olarak döner.

    Ağ katmanının tüm hataları `AsrError`'a çevrilir: çağıran tarafın
    `urllib`'in hata tiplerini tanıması gerekmesin.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise AsrError(
            _("Deşifre sunucusu {code} döndü: {detail}").format(
                code=exc.code, detail=_detail(exc)
            )
        ) from exc
    except urllib.error.URLError as exc:
        raise AsrError(
            _("Deşifre sunucusuna ulaşılamadı ({url}): {reason}").format(
                url=url, reason=exc.reason
            )
        ) from exc
    except OSError as exc:
        # Zaman aşımı buraya düşer: `URLError`'a sarılmadan gelir.
        raise AsrError(
            _("Deşifre sunucusu yanıt vermedi ({url}): {reason}").format(
                url=url, reason=exc
            )
        ) from exc

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AsrError(_("Deşifre sunucusu geçerli JSON döndürmedi.")) from exc


def _detail(error: urllib.error.HTTPError) -> str:
    """Hata gövdesinden kısa, okunabilir bir parça çıkarır.

    Gövde okunamayabilir ya da çok uzun olabilir; ikisi de asıl hatanın
    önüne geçmemeli.
    """
    try:
        body = error.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return error.reason or ""
    return body[:_DETAIL_LIMIT] or (error.reason or "")
