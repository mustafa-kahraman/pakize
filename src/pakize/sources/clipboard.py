"""Panoyu okuyan kaynak ve panoya yazan hedef.

Panoya erişmenin tek bir yolu yok. macOS ve Windows'ta işletim sisteminin
kendi aracı hazır gelir (`pbpaste`/`pbcopy`, PowerShell'in `Get-Clipboard` ve
`Set-Clipboard`'ı). Linux'ta ise pencere sistemine bağlıdır: X11'de
`xclip`/`xsel`, Wayland'de `wl-paste`/`wl-copy`.

Bu modül kurulu araçların arasından en uygununu seçer: önce sistemin kendi
aracı, sonra oturum tipine uyan araç, sonra kalanlar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from ..i18n import _
from ..platforms import IS_MACOS, IS_WINDOWS


class ClipboardError(RuntimeError):
    """Panoya erişilemediğinde oluşan, kullanıcıya gösterilebilir hata."""


@dataclass(frozen=True)
class _Tool:
    """Panoya erişen tek bir harici araç."""

    binary: str
    args: tuple[str, ...]
    session: str | None = None
    """Tercih edildiği pencere sistemi ("wayland"/"x11"); None ise fark etmez."""

    native: bool = False
    """İşletim sisteminin kendi aracı mı? Öyleyse her zaman önce denenir."""

    def command(self) -> list[str]:
        return [self.binary, *self.args]


_POWERSHELL_ARGS = (
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    # Konsolun varsayılan kod sayfası Türkçe metni bozar; çıktıyı UTF-8'e
    # sabitlemeden "ağırlık" gibi kelimeler bozuk döner.
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw",
)

_READERS = (
    _Tool("pbpaste", (), native=True),
    _Tool("pwsh", _POWERSHELL_ARGS, native=True),
    _Tool("powershell", _POWERSHELL_ARGS, native=True),
    _Tool("wl-paste", ("--no-newline",), session="wayland"),
    _Tool("xclip", ("-o", "-selection", "clipboard"), session="x11"),
    _Tool("xsel", ("--clipboard", "--output"), session="x11"),
)

_POWERSHELL_WRITE_ARGS = (
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    # Girdi konsolun kod sayfasıyla değil UTF-8 olarak okunmalı; yoksa Türkçe
    # harfler panoya bozuk gider.
    "[Console]::InputEncoding=[Text.Encoding]::UTF8; $input | Set-Clipboard",
)

_WRITERS = (
    _Tool("pbcopy", (), native=True),
    _Tool("pwsh", _POWERSHELL_WRITE_ARGS, native=True),
    _Tool("powershell", _POWERSHELL_WRITE_ARGS, native=True),
    _Tool("wl-copy", (), session="wayland"),
    _Tool("xclip", ("-i", "-selection", "clipboard"), session="x11"),
    _Tool("xsel", ("--clipboard", "--input"), session="x11"),
)


def read_clipboard() -> str:
    """Pano içeriğini metin olarak döner.

    Pano boşsa boş dizge döner; okuma aracı hiç yoksa `ClipboardError` fırlatır.
    """
    readers = _available(_READERS)
    if not readers:
        raise ClipboardError(_install_hint())

    errors: list[str] = []
    for reader in readers:
        try:
            return _read_with(reader)
        except ClipboardError as exc:
            errors.append(f"{reader.binary}: {exc}")

    raise ClipboardError(
        _("Pano okunamadı — {errors}").format(errors="; ".join(errors))
    )


def write_clipboard(text: str) -> None:
    """Metni panoya koyar; yazma aracı hiç yoksa `ClipboardError` fırlatır."""
    writers = _available(_WRITERS)
    if not writers:
        raise ClipboardError(_install_hint())

    errors: list[str] = []
    for writer in writers:
        try:
            _write_with(writer, text)
            return
        except ClipboardError as exc:
            errors.append(f"{writer.binary}: {exc}")

    raise ClipboardError(
        _("Panoya yazılamadı — {errors}").format(errors="; ".join(errors))
    )


def _install_hint() -> str:
    """Hiç okuyucu bulunamadığında gösterilecek yönlendirme.

    Yalnızca Linux'ta gerçek bir kurulum adımı var; diğerlerinde araç sistemle
    gelir, yokluğu bozuk bir kuruluma işaret eder.
    """
    if IS_MACOS:
        return _("Pano okunamıyor: pbpaste bulunamadı (macOS ile gelmesi gerekir).")
    if IS_WINDOWS:
        return _("Pano okunamıyor: PowerShell PATH üzerinde bulunamadı.")
    return _(
        "Pano okunamıyor: xclip, xsel veya wl-clipboard kurulu değil. "
        "Kurmak için: sudo apt install xclip"
    )


def _available(tools: tuple[_Tool, ...]) -> list[_Tool]:
    """Kurulu araçları en uygun olan başta olacak şekilde sıralar.

    Sistemin kendi aracı önce gelir: macOS'ta XQuartz ile birlikte `xclip` de
    kurulu olabilir, ama orada doğru cevabı veren `pbpaste`'tir.
    """
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    installed = [tool for tool in tools if shutil.which(tool.binary)]
    return sorted(
        installed, key=lambda tool: (not tool.native, tool.session != session)
    )


def _read_with(reader: _Tool) -> str:
    try:
        result = subprocess.run(
            reader.command(),
            capture_output=True,
            # Kod sayfasına güvenmeyiz: araçların hepsi UTF-8 üretir, PowerShell
            # de yukarıdaki komutla buna zorlanır.
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except OSError as exc:
        raise ClipboardError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(_("araç yanıt vermedi")) from exc

    if result.returncode != 0:
        # Boş pano da hata koduyla döner; bunu içerik yokluğu sayarız.
        stderr = (result.stderr or "").strip()
        if _is_empty_clipboard_error(stderr):
            return ""
        raise ClipboardError(
            stderr or _("çıkış kodu {code}").format(code=result.returncode)
        )

    return result.stdout or ""


def _write_with(writer: _Tool, text: str) -> None:
    """Metni tek bir araçla panoya yazar.

    Çıktı boruya bağlanmaz: `xclip` ve `wl-copy` panoyu sunmak için arka
    planda bir kopya bırakır ve bu kopya boruyu açık tutar; Pakize çıktının
    bitmesini beklerken sonsuza dek takılırdı. Hata yalnız çıkış kodundan
    anlaşılır.
    """
    try:
        result = subprocess.run(
            writer.command(),
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except OSError as exc:
        raise ClipboardError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClipboardError(_("araç yanıt vermedi")) from exc

    if result.returncode != 0:
        raise ClipboardError(_("çıkış kodu {code}").format(code=result.returncode))


def _is_empty_clipboard_error(stderr: str) -> bool:
    """Araçların "pano boş" anlamına gelen hata metinlerini tanır."""
    lowered = stderr.lower()
    return "target string not available" in lowered or "no selection" in lowered
