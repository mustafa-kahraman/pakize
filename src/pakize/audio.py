"""Ses dosyalarını birleştirme ve çalma — ffmpeg araç zinciri sarmalayıcısı."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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
    ffplay = _require_binary("ffplay")
    _run([ffplay, "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error", str(path)])


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
