"""İşletim sistemine göre değişen küçük kararlar.

Pakize'nin çekirdeği taşınabilir: metin ayrıştırma, boru hattı ve motorlar üç
platformda da aynı kodu çalıştırır. Yalnızca birkaç noktada sisteme sormak
gerekir — ayarların nereye yazılacağı, eksik bir aracın nasıl kurulacağı.

Bu kararların tek yeri burasıdır. Aksi hâlde her modül kendi `sys.platform`
kontrolünü taşır, biri güncellenirken diğeri unutulurdu.
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import Callable

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def config_home() -> Path:
    """Kullanıcı ayarlarının kök dizini.

    `XDG_CONFIG_HOME` her platformda önceliklidir; taşınabilir kurulumda ve
    testte ayarları tek değişkenle yönlendirmeye yarar.

    macOS'ta `~/Library/Application Support` yerine `~/.config` seçildi: elle
    düzenlenen bir TOML dosyası, terminal araçlarının alışılmış yerinde
    durmalı — Finder'ın gizlediği bir klasörde değil.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)

    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)

    return Path.home() / ".config"


def cache_home() -> Path:
    """Silinse de yeniden üretilebilen dosyaların kök dizini.

    `XDG_CACHE_HOME` her platformda önceliklidir. macOS'ta `config_home` ile
    aynı gerekçeyle `~/Library/Caches` yerine `~/.cache` seçildi.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg)

    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local)

    return Path.home() / ".cache"


def die_with_parent() -> Callable[[], None] | None:
    """Alt sürecin, onu başlatan süreç ölünce kendiliğinden kapanmasını sağlar.

    `subprocess.Popen(preexec_fn=...)` için bir işlev döner. Linux'ta
    çekirdeğin `PR_SET_PDEATHSIG` ayarını kullanır: Pakize `kill -9` ile
    öldürülse bile alt süreç SIGTERM alır. Pakize'nin normal yolları alt
    süreci zaten kapatır; bu, onların hiç çalışamadığı durumun güvencesidir.

    Başka platformlarda karşılığı yok; None döner. `ctypes`'sız derlenmiş
    Python'larda da None döner: güvence eksik kalır, Pakize çalışmaya devam
    eder.
    """
    if not sys.platform.startswith("linux"):
        return None

    try:
        import ctypes

        # Kütüphane üst süreçte yüklenir; alt süreç fork ile exec arasında
        # yalnızca çağrıyı yapar, orada dosya aramak riskli olurdu.
        libc = ctypes.CDLL(None, use_errno=True)
    except (ImportError, OSError):
        return None

    def set_parent_death_signal() -> None:
        libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)

    return set_parent_death_signal


_PR_SET_PDEATHSIG = 1
"""`linux/prctl.h` içindeki sabit."""


def temp_root() -> Path:
    """Geçici çıktıların kök dizini.

    Linux'ta `/tmp`, Windows'ta `%TEMP%`, macOS'ta oturuma özel
    `/var/folders/...` klasörüne denk gelir.
    """
    return Path(tempfile.gettempdir())


_INSTALL_COMMANDS: dict[str, tuple[str, str, str]] = {
    # araç: (Linux, macOS, Windows)
    "ffmpeg": (
        "sudo apt install ffmpeg",
        "brew install ffmpeg",
        "winget install Gyan.FFmpeg",
    ),
    "calibre": (
        "sudo apt install calibre",
        "brew install --cask calibre",
        "winget install calibre.calibre",
    ),
}


def install_hint(tool: str) -> str:
    """Eksik bir aracın bu platformdaki kurulum komutu.

    Hata mesajında yanlış paket yöneticisini önermek, kullanıcıyı çıkmaz bir
    aramaya yolluyor; bu yüzden ipucu da platforma göre seçilir.
    """
    linux, macos, windows = _INSTALL_COMMANDS[tool]
    if IS_WINDOWS:
        return windows
    if IS_MACOS:
        return macos
    return linux
