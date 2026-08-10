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

STATE_NAME = "pakize-playing"


def state_dir() -> Path:
    """Süreç kayıtlarının tutulduğu dizin.

    Her çalan süreç için ayrı bir dosya tutulur. Tek dosya kullanmak, aynı
    anda iki Pakize çaldığında birinin kaydını ezip o sürecin durdurulamaz
    hâle gelmesine yol açıyordu.
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / STATE_NAME


def register(pid: int) -> None:
    """Çalmayı yürüten süreci kaydeder."""
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / str(pid)).write_text(str(pid), encoding="utf-8")


def clear(pid: int) -> None:
    """Bir sürecin kaydını siler; diğerlerine dokunmaz."""
    (state_dir() / str(pid)).unlink(missing_ok=True)


def running_pids() -> list[int]:
    """Kayıtlı ve hâlâ yaşayan Pakize süreçleri; en yeniden eskiye.

    Bayat kayıtlar sessizce temizlenir.
    """
    directory = state_dir()
    if not directory.is_dir():
        return []

    yasayanlar: list[tuple[float, int]] = []
    for entry in directory.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if not _is_pakize(pid):
            entry.unlink(missing_ok=True)
            continue
        yasayanlar.append((entry.stat().st_mtime, pid))

    return [pid for _, pid in sorted(yasayanlar, reverse=True)]


def running_pid() -> int | None:
    """En son kaydedilen yaşayan süreç; yoksa None."""
    pids = running_pids()
    return pids[0] if pids else None


PLAYER_COMM = "ffplay"
"""Çalmayı yürüten sürecin çekirdekteki adı."""

_STOPPED_STATE = "T"
"""`/proc/<pid>/stat` içinde duraklatılmış süreci gösteren durum harfi."""


def pause(pid: int) -> bool:
    """Sürecin çalma alt süreçlerini duraklatır.

    Duraklatılacak bir şey yoksa False döner.
    """
    return _signal_players(pid, signal.SIGSTOP)


def resume(pid: int) -> bool:
    """Duraklatılmış çalmayı sürdürür."""
    return _signal_players(pid, signal.SIGCONT)


def is_paused(pid: int) -> bool:
    """Çalma şu an duraklatılmış mı?"""
    players = _players(pid)
    return bool(players) and all(state == _STOPPED_STATE for _, state in players)


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


def _signal_players(pid: int, sig: int) -> bool:
    """Çalma alt süreçlerinin tümüne sinyal gönderir; hiçbiri yoksa False."""
    gonderildi = False
    for player_pid, _ in _players(pid):
        try:
            os.kill(player_pid, sig)
        except (ProcessLookupError, PermissionError):
            continue
        gonderildi = True
    return gonderildi


def _players(pid: int) -> list[tuple[int, str]]:
    """Sürecin çalma alt süreçlerini (numara, durum) çiftleri olarak döner.

    Çalan süreci ayrı bir dosyada tutmak yerine işletim sisteminden okuruz:
    tek doğruluk kaynağı çekirdek olur, kayıt ile gerçek arasında kayma olmaz.
    """
    try:
        adaylar = [
            int(entry.name) for entry in Path("/proc").iterdir() if entry.name.isdigit()
        ]
    except OSError:
        return []

    bulunan: list[tuple[int, str]] = []
    for aday in adaylar:
        okunan = _read_stat(aday)
        if okunan is None:
            continue
        comm, state, ppid = okunan
        if ppid == pid and comm == PLAYER_COMM:
            bulunan.append((aday, state))
    return bulunan


def _read_stat(pid: int) -> tuple[str, str, int] | None:
    """`/proc/<pid>/stat` dosyasından (komut adı, durum, ebeveyn) okur."""
    try:
        icerik = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _parse_stat_line(icerik)


def _parse_stat_line(satir: str) -> tuple[str, str, int] | None:
    """`stat` satırını (komut adı, durum, ebeveyn) üçlüsüne ayrıştırır.

    Komut adı parantez içindedir ve boşluk içerebilir; bu yüzden sondaki
    parantezden bölmek, alanlara boşlukla ayırmaktan güvenlidir.
    """
    bas, ayrac, kalan = satir.rpartition(")")
    if not ayrac or "(" not in bas:
        return None

    comm = bas.partition("(")[2]
    alanlar = kalan.split()
    if len(alanlar) < 2:
        return None

    try:
        return comm, alanlar[0], int(alanlar[1])
    except ValueError:
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
