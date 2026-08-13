"""Ses dosyalarını birleştirme ve çalma — ffmpeg araç zinciri sarmalayıcısı."""

from __future__ import annotations

import asyncio
import shutil
import signal
import subprocess
import threading
from pathlib import Path

import psutil

from .i18n import _
from .platforms import install_hint

_player_lock = threading.Lock()
_player = None
"""Çalmakta olan ffplay süreci; `stop_playback` bunun üzerinden keser."""

_stopped = False
"""Çalma `stop_playback` ile mi kesildi?

Çıkış kodundan anlaşılamıyor: Windows'ta sonlandırılan süreç sıradan bir
hatayla aynı kodu döndürür. Niyeti kodun kendisinden okumaya çalışmak yerine
kaydederiz.
"""

_CTRL_C_EXIT = 0xC000013A
"""Windows'ta Ctrl+C ile kesilen sürecin çıkış kodu (STATUS_CONTROL_C_EXIT)."""

_TERMINATION_CODES = frozenset(
    {
        -signal.SIGTERM,
        -signal.SIGINT,
        128 + signal.SIGTERM,
        128 + signal.SIGINT,
        _CTRL_C_EXIT,
        # Aynı kod, işaretli tam sayı olarak okunduğunda.
        _CTRL_C_EXIT - 2**32,
    }
)
"""Sonlandırma sinyaliyle biten çalmanın dönebileceği çıkış kodları."""


class AudioError(RuntimeError):
    """ffmpeg/ffplay ile ilgili, kullanıcıya gösterilebilir hata."""


def concat(parts: list[Path], destination: Path) -> Path:
    """Ses parçalarını sırayı koruyarak tek dosyada birleştirir.

    Parçalar hedefle aynı biçimdeyse yeniden kodlanmaz; `-c copy` hem hızlı
    hem kayıpsızdır. Biçim farklıysa (Piper WAV üretir, hedef ise .mp3 olabilir)
    dönüştürme yapılır — aksi hâlde uzantısı mp3 olan bir WAV dosyası çıkardı.
    """
    if not parts:
        raise AudioError(_("Birleştirilecek ses parçası yok"))

    destination.parent.mkdir(parents=True, exist_ok=True)
    donusum_gerekli = _needs_transcode(parts, destination)

    if len(parts) == 1 and not donusum_gerekli:
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
                *_codec_args(donusum_gerekli),
                str(destination),
            ]
        )
    finally:
        list_file.unlink(missing_ok=True)

    return destination


def _needs_transcode(parts: list[Path], destination: Path) -> bool:
    """Parçaların biçimi hedefinkinden farklı mı?"""
    hedef = destination.suffix.lower()
    return any(part.suffix.lower() != hedef for part in parts)


def _codec_args(donusum_gerekli: bool) -> list[str]:
    return ["-vn"] if donusum_gerekli else ["-c", "copy"]


def play(path: Path) -> None:
    """Ses dosyasını ffplay ile, pencere açmadan ve sonunda kapanacak şekilde çalar."""
    process = subprocess.Popen(
        _play_command(path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    _set_player(process)
    try:
        # `_` çeviri fonksiyonu olduğu için atılacak değer `_out` adını alır.
        _out, stderr = process.communicate()
    finally:
        kesildi = _clear_player(process)
    _check_player_exit(process.returncode, stderr, kesildi)


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
        _out, stderr = await process.communicate()
    finally:
        kesildi = _clear_player(process)
    _check_player_exit(process.returncode, stderr, kesildi)


def stop_playback() -> bool:
    """Çalmakta olan sesi sonlandırır; çalan bir şey yoksa False döner."""
    global _stopped
    with _player_lock:
        process = _player
        if process is not None:
            _stopped = True
    if process is None:
        return False

    # Sıra önemli: devam ettirme sonlandırmadan ÖNCE gelmeli.
    _resume(process)
    try:
        process.terminate()
    except (ProcessLookupError, OSError):
        return False
    return True


def _resume(process) -> None:
    """Duraklatılmış olabilecek süreci devam ettirir.

    `pakize pause` ile durdurulmuş bir süreç sonlandırma isteğini işleyemez.
    Beklemede bırakıp sonradan devam ettirmek yetmiyor: ffplay bu durumda
    isteği yutup çalmayı sürdürüyor. Önce devam ettirip sonra sonlandırmak
    gerekiyor.
    """
    try:
        psutil.Process(process.pid).resume()
    except (psutil.Error, OSError):
        return


def _set_player(process) -> None:
    """Çalan süreci kaydeder.

    Aynı anda tek bir ses çaldığı için modül düzeyinde tek bir kayıt yeter;
    `stop_playback` dışarıdan bu kayda bakarak sesi kesebilir.
    """
    global _player, _stopped
    with _player_lock:
        _player = process
        _stopped = False


def _clear_player(process) -> bool:
    """Kaydı temizler; çalmanın kasıtlı olarak kesilip kesilmediğini döner."""
    global _player, _stopped
    with _player_lock:
        if _player is not process:
            return False
        _player = None
        kesildi, _stopped = _stopped, False
        return kesildi


def _check_player_exit(
    returncode: int | None, stderr: bytes | None, kesildi: bool = False
) -> None:
    """ffplay çıkışını değerlendirir.

    Kasıtlı olarak kesilen ya da sonlandırma sinyaliyle biten çalma hata
    değildir; `pakize stop` ve Ctrl+C beklenen bir sonlanma yoludur.
    """
    if kesildi or returncode in (0, None) or returncode in _TERMINATION_CODES:
        return
    detail = (stderr or b"").decode(errors="replace").strip()
    raise AudioError(
        _("ffplay hata verdi (kod {code}): {error}").format(
            code=returncode, error=detail
        )
    )


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
            _("{name} bulunamadı. Kurmak için: {hint}").format(
                name=name, hint=install_hint("ffmpeg")
            )
        )
    return path


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioError(
            _("{name} hata verdi (kod {code}): {error}").format(
                name=Path(command[0]).name,
                code=result.returncode,
                error=result.stderr.strip(),
            )
        )
