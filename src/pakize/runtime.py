"""Çalmakta olan seslendirmenin süreç kaydı ve denetimi.

`pakize dur` ve `pakize duraklat`, çalmayı başlatan sürece ulaşabilmek için bu
kaydı okur. Kayıt geçici dizin altında tutulur; oturum kapanınca işletim
sistemi temizler.

Kayıt yalnızca bir ipucudur: süreç kimlikleri yeniden kullanılabildiği için
okurken sürecin gerçekten Pakize olduğu doğrulanır.

Süreç ağacına doğrudan işletim sistemi arayüzleriyle değil `psutil` üzerinden
bakarız: Linux'ta `/proc`, macOS'ta `sysctl`, Windows'ta `NtQuerySystemInfo`
gerekir ve duraklatmanın Windows karşılığı sinyal değil `NtSuspendProcess`'tir.
Tek kod yolu ancak bu soyutlamayla mümkün.
"""

from __future__ import annotations

import os
from pathlib import Path

import psutil

from .platforms import temp_root

STATE_NAME = "pakize-playing"

PLAYER_COMM = "ffplay"
"""Çalmayı yürüten sürecin adı (Windows'ta `ffplay.exe` olarak görünür)."""


def state_dir() -> Path:
    """Süreç kayıtlarının tutulduğu dizin.

    Her çalan süreç için ayrı bir dosya tutulur. Tek dosya kullanmak, aynı
    anda iki Pakize çaldığında birinin kaydını ezip o sürecin durdurulamaz
    hâle gelmesine yol açıyordu.
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else temp_root()
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


def pause(pid: int) -> bool:
    """Sürecin çalma alt süreçlerini duraklatır.

    Duraklatılacak bir şey yoksa False döner.
    """
    return _apply(pid, "suspend")


def resume(pid: int) -> bool:
    """Duraklatılmış çalmayı sürdürür."""
    return _apply(pid, "resume")


def is_paused(pid: int) -> bool:
    """Çalma şu an duraklatılmış mı?"""
    players = _players(pid)
    return bool(players) and all(_is_suspended(player) for player in players)


def stop(pid: int) -> bool:
    """Çalmayı keser ve süreci sonlandırır.

    Önce çalan sesler susturulur, sonra ana süreç sonlandırılır. Sıra kasıtlı:
    Windows'ta süreç sonlandırma sinyal işleyicisini çalıştırmaz, dolayısıyla
    ana süreç kendi ffplay'ini kesemeden ölür ve ses öksüz kalıp çalmayı
    sürdürürdü.

    Süreç zaten ölmüşse False döner; çağıran bunu hata saymamalıdır.
    """
    _terminate_players(pid)

    try:
        psutil.Process(pid).terminate()
    except psutil.NoSuchProcess:
        clear(pid)
        return False
    except (psutil.Error, OSError):
        return False
    return True


def _apply(pid: int, eylem: str) -> bool:
    """Çalma alt süreçlerinin tümüne bir eylemi uygular; hiçbiri yoksa False."""
    uygulandi = False
    for player in _players(pid):
        # Kısa devre yapılmamalı: biri başarısız olsa da diğerlerine uygulanır.
        if _try(player, eylem):
            uygulandi = True
    return uygulandi


def _terminate_players(pid: int) -> None:
    """Çalan sesleri keser.

    Sıra önemli: duraklatılmış bir süreç sonlandırma isteğini işleyemez, bu
    yüzden önce devam ettirilir. Ters sırada ffplay isteği yutup çalmayı
    sürdürüyor.
    """
    for player in _players(pid):
        _try(player, "resume")
        _try(player, "terminate")


def _try(process: psutil.Process, eylem: str) -> bool:
    """Süreç üzerinde bir eylemi dener; uygulanamadıysa False döner.

    Süreç iki okuma arasında ölmüş olabilir; bu olağan bir yarış, hata değil.
    Devam ettirme başarısız olsa bile sonlandırmanın denenmesi gerektiği için
    hata yutma tek tek eylemlerin çevresindedir.
    """
    try:
        getattr(process, eylem)()
    except (psutil.Error, OSError):
        return False
    return True


def _players(pid: int) -> list[psutil.Process]:
    """Sürecin çalma alt süreçlerini döner.

    Çalan süreci ayrı bir dosyada tutmak yerine işletim sisteminden okuruz:
    tek doğruluk kaynağı çekirdek olur, kayıt ile gerçek arasında kayma olmaz.
    """
    try:
        children = psutil.Process(pid).children(recursive=True)
    except (psutil.Error, OSError):
        return []
    return [child for child in children if _is_player(child)]


def _is_player(process: psutil.Process) -> bool:
    """Süreç, çalmayı yürüten ffplay mi?

    Uzantı ayıklanır: aynı süreç Windows'ta `ffplay.exe` adıyla görünür.
    """
    try:
        return Path(process.name()).stem.lower() == PLAYER_COMM
    except (psutil.Error, OSError):
        return False


def _is_suspended(process: psutil.Process) -> bool:
    """Süreç duraklatılmış durumda mı?"""
    try:
        return process.status() == psutil.STATUS_STOPPED
    except (psutil.Error, OSError):
        return False


def _is_pakize(pid: int) -> bool:
    """Süreç yaşıyor mu ve gerçekten Pakize mi?

    Komut satırına bakmak, kayıt bayatladıktan sonra aynı numarayı almış
    alakasız bir sürecin öldürülmesini engeller.
    """
    try:
        cmdline = psutil.Process(pid).cmdline()
    except (psutil.Error, OSError):
        return False
    return any("pakize" in arg.lower() for arg in cmdline)
