"""Hatayı sesle bildiren hazır uyarılar.

Pakize çoğunlukla bir klavye kısayolundan çalışır; orada terminal yoktur ve
ekrana basılan hata görünmez. Kullanıcı sesin neden gelmediğini anlamaz,
kısayola tekrar tekrar basar. Çeviri kısıtlamasında bu, engeli uzatır.

Uyarı ilk gerektiğinde Pakize'nin kendi sesiyle bir kez üretilir ve
önbellekte saklanır; sonraki seferlerde servise gitmeden çalınır. Dosya
pakete konmaz: kullanıcının seçtiği sesle ve dilde konuşmalı.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

from .config import Config
from .i18n import in_language, voice_language
from .pipeline import synthesize
from .platforms import cache_home


def notices_dir() -> Path:
    return cache_home() / "pakize" / "notices"


def rate_limit_notice(config: Config) -> Path:
    """Çeviri kısıtlaması uyarısının ses dosyasını döner; yoksa üretir."""
    text = in_language(
        "Çeviri şu an kullanılamıyor. Google kısa bir süreliğine sınır koydu. "
        "Birkaç dakika bekleyip tekrar dene; hemen denersen bekleme uzar.",
        voice_language(config.voice),
    )
    return _cached_notice("rate-limit", text, config)


def dictation_notice(message: str, config: Config) -> Path:
    """Dikte hatasını okuyan ses dosyasını döner; yoksa üretir.

    Dikte tümüyle kısayoldan yürür; hatanın tek görünür yeri sestir. Mesaj
    olduğu gibi okunur: konuşan kullanıcı "model bulunamadı" ile "pano yok"
    arasındaki farkı duymalı. Aynı mesaj ikinci kez üretilmez.
    """
    return _cached_notice("dictate", message, config)


def _cached_notice(name: str, text: str, config: Config) -> Path:
    """Uyarıyı önbellekten döner; yoksa seslendirip önbelleğe yazar.

    Dosya adı metni ve sesi etkileyen ayarları taşır: ses ya da hız
    değişince eski kayıt çalınmaz, yenisi üretilir.
    """
    target = notices_dir() / f"{name}-{_fingerprint(text, config)}.mp3"
    if target.is_file():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    # Kısayola art arda basılırsa iki süreç aynı anda üretebilir; yarım
    # yazılmış dosya çalınmasın diye önce geçici ada yazılıp taşınır. Uzantı
    # sonda kalmalı: ffmpeg çıktı biçimini ondan seçiyor.
    partial = target.with_name(f".{target.stem}.{os.getpid()}{target.suffix}")
    try:
        # Uyarının kendisi çevrilmez: çeviri zaten kullanılamıyor.
        synthesize(text, partial, replace(config, translate_to=None, stream=False))
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _fingerprint(text: str, config: Config) -> str:
    key = "\n".join(
        str(value)
        for value in (
            text,
            config.engine,
            config.voice,
            config.rate,
            config.pitch_hz,
            config.volume,
        )
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
