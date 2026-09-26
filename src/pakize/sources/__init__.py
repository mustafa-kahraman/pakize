"""Pakize'ye metin sağlayan kaynaklar.

Her kaynak yalnızca düz metin döndürür; ayrıştırma ve seslendirme boru hattının
işidir. Böylece yeni bir kaynak eklemek boru hattına dokunmadan mümkün olur.
"""

from .clipboard import ClipboardError, read_clipboard, write_clipboard
from .transcript import Roles, TranscriptError, collect, find_sessions, latest_session

__all__ = [
    "ClipboardError",
    "read_clipboard",
    "write_clipboard",
    "Roles",
    "TranscriptError",
    "collect",
    "find_sessions",
    "latest_session",
]
