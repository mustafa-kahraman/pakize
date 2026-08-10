"""Pakize'ye metin sağlayan kaynaklar.

Her kaynak yalnızca düz metin döndürür; ayrıştırma ve seslendirme boru hattının
işidir. Böylece yeni bir kaynak eklemek boru hattına dokunmadan mümkün olur.
"""

from .clipboard import ClipboardError, read_clipboard

__all__ = ["ClipboardError", "read_clipboard"]
