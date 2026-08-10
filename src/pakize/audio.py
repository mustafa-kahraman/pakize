"""Ses dosyalarını birleştirme ve çalma — ffmpeg araç zinciri sarmalayıcısı."""

from __future__ import annotations

import asyncio
import shutil
import signal
import subprocess
import threading
from pathlib import Path

_player_lock = threading.Lock()
_player = None
"""Çalmakta olan ffplay süreci; `stop_playback` bunun üzerinden keser."""

_TERMINATION_CODES = frozenset(
    {-signal.SIGTERM, -signal.SIGINT, 128 + signal.SIGTERM, 128 + signal.SIGINT}
)
"""Sonlandırma sinyaliyle biten çalmanın dönebileceği çıkış kodları."""


class AudioError(RuntimeError):
    """ffmpeg/ffplay ile ilgili, kullanıcıya gösterilebilir hata."""


def concat(parts: list[Path], destination: Path) -> Path:
    """Ses parçalarını sırayı koruyarak tek dosyada birleştirir.

    Parçaların tümü aynı motordan ve aynı kodekten geldiği için yeniden
    kodlamaya gerek yoktur; `-c copy` hem hızlı hem kayıpsızdır.
    """
    if not parts:
        raise AudioError("Birleştirilecek ses parçası yok")

    destination.parent.mkdir(parents=True, exist_ok=True)

    if len(parts) == 1:
        shutil.copyfile(parts[0], destination)
        return destination

    ffmpeg = _require_binary("ffmpeg")
    list_file = destination.parent / f".{destination.stem}.concat.txt"
    list_file.write_text(
        "".join(f"file {_quote(p)}\n" for p in parts), encoding="utf-8"
    )

    try:
        _run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(destination),
            ]
        )
    finally:
        list_file.unlink(missing_ok=True)

    return destination


def play(path: Path) -> None:
    """Ses dosyasını ffplay ile, pencere açmadan ve sonunda kapanacak şekilde çalar."""
    process = subprocess.Popen(
        _play_command(path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    _set_player(process)
    try:
        _, stderr = process.communicate()
    finally:
        _clear_player(process)
    _check_player_exit(process.returncode, stderr)


async def play_async(path: Path) -> None:
    """`play` ile aynı iş; olay döngüsünü bloklamaz.

    Akıcı çalmada üretim ve çalma aynı anda sürdüğü için gereklidir.
    """
    process = await asyncio.create_subprocess_exec(
        *_play_command(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _set_player(process)
    try:
        _, stderr = await process.communicate()
    finally:
        _clear_player(process)
    _check_player_exit(process.returncode, stderr)


def stop_playback() -> bool:
    """Çalmakta olan sesi sonlandırır; çalan bir şey yoksa False döner."""
    with _player_lock:
        process = _player
    if process is None:
        return False
    try:
        process.terminate()
    except (ProcessLookupError, OSError):
        return False
    return True


def _set_player(process) -> None:
    """Çalan süreci kaydeder.

    Aynı anda tek bir ses çaldığı için modül düzeyinde tek bir kayıt yeter;
    `stop_playback` dışarıdan bu kayda bakarak sesi kesebilir.
    """
    global _player
    with _player_lock:
        _player = process


def _clear_player(process) -> None:
    global _player
    with _player_lock:
        if _player is process:
            _player = None


def _check_player_exit(returncode: int | None, stderr: bytes | None) -> None:
    """ffplay çıkışını değerlendirir.

    Sonlandırma sinyaliyle biten çalma hata değildir; `pakize dur` ve Ctrl+C
    beklenen bir sonlanma yoludur.
    """
    if returncode in (0, None) or returncode in _TERMINATION_CODES:
        return
    detay = (stderr or b"").decode(errors="replace").strip()
    raise AudioError(f"ffplay hata verdi (kod {returncode}): {detay}")


def _play_command(path: Path) -> list[str]:
    ffplay = _require_binary("ffplay")
    return [
        ffplay,
        "-nodisp",
        "-autoexit",
        "-hide_banner",
        "-loglevel",
        "error",
        str(path),
    ]


def _quote(path: Path) -> str:
    """Yolu ffmpeg concat demuxer'ının beklediği biçimde tırnaklar.

    Demuxer tek tırnaklı dizgide, tek tırnağın kendisini `'\\''` ile bekler.
    """
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"'{escaped}'"


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise AudioError(
            f"{name} bulunamadı. Kurmak için: sudo apt install ffmpeg"
        )
    return path


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioError(
            f"{Path(command[0]).name} hata verdi (kod {result.returncode}): "
            f"{result.stderr.strip()}"
        )
