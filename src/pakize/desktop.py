"""Masaüstü bildirimi: sesin ulaşamadığı yerde son çare.

Pakize çoğunlukla bir klavye kısayolundan çalışır; orada terminal yoktur ve
hatalar sesle bildirilir. Ses de çalınamıyorsa (ffplay kurulu değil, ses
aygıtı yok) kullanıcı hiçbir şey duymaz ve nedenini anlayamaz. Bildirim bu
boşluğu kapatır.

Linux'ta `notify-send` (libnotify), macOS'ta sistemle gelen `osascript`
kullanılır. Windows'ta sistemle gelen bir komut satırı bildirim aracı yok;
orada bildirim gönderilmez.

Bildirim hiçbir zaman hata fırlatmaz: asıl hatanın önüne geçmemeli.
"""

from __future__ import annotations

import shutil
import subprocess

from .platforms import IS_MACOS, IS_WINDOWS

TITLE = "Pakize"

TIMEOUT_SECONDS = 5


def notify(message: str, title: str = TITLE) -> bool:
    """Masaüstünde bir bildirim gösterir; gösterilemezse False döner."""
    command = _command(title, message)
    if command is None:
        return False
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _command(title: str, message: str) -> list[str] | None:
    if IS_WINDOWS:
        return None

    if IS_MACOS:
        osascript = shutil.which("osascript")
        if osascript is None:
            return None
        # Metin betiğin içine gömülmez, argüman olarak verilir: tırnak ya da
        # ters bölü içeren bir hata mesajı betiği bozamaz.
        return [
            osascript,
            "-e", "on run argv",
            "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
            "-e", "end run",
            title,
            message,
        ]  # fmt: skip

    notify_send = shutil.which("notify-send")
    if notify_send is None:
        return None
    # `--` sonrası seçenek sayılmaz: "-" ile başlayan bir mesaj bayrak sanılmaz.
    return [notify_send, "--app-name", TITLE, "--", title, message]
