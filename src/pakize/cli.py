"""Pakize komut satırı arayüzü.

Bu modül ince bir kabuktur: girdiyi toplar, config'i bayraklarla ezer ve
`pipeline`'ı çağırır. Hiçbir iş mantığı burada yaşamaz.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import typer

from . import audio
from .config import Config, config_path, load_config
from .engines import EdgeEngine, EngineError, available_engines
from .models import SegmentType
from .pipeline import plan_speech, synthesize

app = typer.Typer(
    help="Metni ses dosyasına çevirir; kod bloklarını okumaz.",
    add_completion=False,
    no_args_is_help=True,
)

_SEGMENT_LABELS = {
    SegmentType.CODE_BLOCK: "kod bloğu",
    SegmentType.TABLE: "tablo",
    SegmentType.URL: "bağlantı",
    SegmentType.INLINE_CODE: "satır içi kod",
    SegmentType.HORIZONTAL_RULE: "yatay çizgi",
}


@app.command()
def speak(
    source: Path = typer.Argument(
        None,
        help="Okunacak metin dosyası. Verilmezse stdin'den okunur.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Üretilecek ses dosyasının yolu."
    ),
    voice: str = typer.Option(None, "--voice", "-v", help="TTS sesi."),
    rate: float = typer.Option(
        None, "--rate", "-r", help="Konuşma hızı çarpanı (örn. 1.15)."
    ),
    engine: str = typer.Option(None, "--engine", "-e", help="Kullanılacak motor."),
    play: bool = typer.Option(
        True, "--play/--no-play", help="Ses hazır olunca otomatik çal."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Ses üretmeden neyin okunacağını göster."
    ),
) -> None:
    """Bir metni seslendirir."""
    text = _read_source(source)
    if not text.strip():
        typer.secho("Girdi boş.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    config = _resolved_config(voice=voice, rate=rate, engine=engine)

    if dry_run:
        _print_plan(text, config)
        return

    destination = output or _default_output_path()
    try:
        result = synthesize(text, destination, config, progress=_progress)
    except EngineError as exc:
        typer.secho(f"\nHata: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except audio.AudioError as exc:
        typer.secho(f"\nSes hatası: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo()
    _print_skipped(result.plan.skipped)
    typer.secho(f"Hazır: {result.output}", fg=typer.colors.GREEN)
    if result.engine != config.engine:
        typer.secho(
            f"Not: {config.engine} motoru çalışmadı, {result.engine} kullanıldı.",
            fg=typer.colors.YELLOW,
        )

    if play:
        audio.play(result.output)


@app.command()
def voices(
    language: str = typer.Option(
        "tr", "--language", "-l", help="Dil ön eki (örn. tr, en-US). Tümü için: all."
    ),
) -> None:
    """Edge motorunun sunduğu sesleri listeler."""
    import asyncio

    prefix = None if language.lower() == "all" else language
    found = asyncio.run(EdgeEngine.list_voices(prefix))
    if not found:
        typer.secho(f"{language} için ses bulunamadı.", fg=typer.colors.YELLOW)
        return

    for entry in found:
        typer.echo(f"{entry['ShortName']:<34} {entry['Gender']:<8} {entry['Locale']}")


@app.command("config")
def show_config() -> None:
    """Etkin ayarları ve config dosyasının yolunu gösterir."""
    path = config_path()
    config = load_config(path)

    typer.echo(f"Config dosyası: {path}" + ("" if path.is_file() else " (yok)"))
    typer.echo(f"Motor          : {config.engine} (tanınanlar: {', '.join(available_engines())})")
    typer.echo(f"Yedek motor    : {config.fallback_engine or '—'}")
    typer.echo(f"Ses            : {config.voice}")
    typer.echo(f"Hız            : {config.rate} ({config.rate_percent()})")
    typer.echo(f"Parça sınırı   : {config.max_chunk_chars} karakter")
    typer.echo("Politika:")
    for segment_type, action in sorted(config.policy.items(), key=lambda kv: kv[0].value):
        typer.echo(f"  {segment_type.value:<18} {action.value}")


def _read_source(source: Path | None) -> str:
    if source is not None:
        return source.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        typer.secho(
            "Bir dosya yolu ver ya da metni stdin'den boruyla aktar.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    return sys.stdin.read()


def _resolved_config(voice: str | None, rate: float | None, engine: str | None) -> Config:
    """Dosyadan gelen ayarları CLI bayraklarıyla ezer."""
    config = load_config()
    overrides = {
        key: value
        for key, value in (("voice", voice), ("rate", rate), ("engine", engine))
        if value is not None
    }
    return replace(config, **overrides) if overrides else config


def _default_output_path() -> Path:
    """Çıktı verilmediğinde kullanılacak, zaman damgalı kalıcı yol.

    Çalışma dizinini kirletmemek için XDG veri dizinine yazarız.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.home() / ".local" / "share" / "pakize" / f"{stamp}.mp3"


def _progress(done: int, total: int) -> None:
    typer.echo(f"\rSeslendiriliyor: {done}/{total} parça", nl=False)


def _print_plan(text: str, config: Config) -> None:
    plan = plan_speech(text, config)
    typer.secho(
        f"{len(plan.chunks)} parça, toplam {plan.total_chars} karakter okunacak.",
        fg=typer.colors.CYAN,
    )
    _print_skipped(plan.skipped)
    for chunk in plan.chunks:
        typer.echo(f"\n--- parça {chunk.index + 1} ---")
        typer.echo(chunk.text)


def _print_skipped(skipped: dict[SegmentType, int]) -> None:
    if not skipped:
        return
    parts = [
        f"{count} {_SEGMENT_LABELS.get(segment_type, segment_type.value)}"
        for segment_type, count in sorted(skipped.items(), key=lambda kv: kv[0].value)
    ]
    typer.secho("Okunmadı: " + ", ".join(parts), fg=typer.colors.YELLOW)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
