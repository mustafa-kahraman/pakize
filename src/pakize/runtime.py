"""Çalmakta olan seslendirmenin süreç kaydı.

`pakize dur`, çalmayı başlatan sürece ulaşabilmek için bu kaydı okur. Kayıt
`XDG_RUNTIME_DIR` altında tutulur; oturum kapanınca işletim sistemi temizler.

Kayıt yalnızca bir ipucudur: süreç kimlikleri yeniden kullanılabildiği için
okurken sürecin gerçekten Pakize olduğu doğrulanır.
"""

from __future__ import annotations

import os
import signal
import tempfile
from pathlib import Path

STATE_NAME = "pakize-playing.pid"


def state_path() -> Path:
    """Süreç kaydının tutulduğu dosya."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / STATE_NAME


def register(pid: int) -> None:
    """Çalmayı yürüten süreci kaydeder."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def clear(pid: int | None = None) -> None:
    """Kaydı siler.

    `pid` verilirse yalnızca kayıt o sürece aitse silinir; böylece art arda
    çalışan iki Pakize birbirinin kaydını düşürmez.
    """
    path = state_path()
    if pid is not None and _read_pid(path) != pid:
        return
    path.unlink(missing_ok=True)


def running_pid() -> int | None:
    """Kayıtlı ve hâlâ yaşayan Pakize sürecini döner; yoksa None.

    Bayat kayıt bulunursa sessizce temizlenir.
    """
    path = state_path()
    pid = _read_pid(path)
    if pid is None:
        return None
    if not _is_pakize(pid):
        path.unlink(missing_ok=True)
        return None
    return pid


def stop(pid: int) -> bool:
    """Sürece nazik sonlandırma sinyali gönderir.

    Süreç zaten ölmüşse False döner; çağıran bunu hata saymamalıdır.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear(pid)
        return False
    except PermissionError:
        return False
    return True


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _is_pakize(pid: int) -> bool:
    """Süreç yaşıyor mu ve gerçekten Pakize mi?

    Komut satırına bakmak, kayıt bayatladıktan sonra aynı numarayı almış
    alakasız bir sürecin öldürülmesini engeller.
    """
    cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        return b"pakize" in cmdline.read_bytes()
    except OSError:
        return False
