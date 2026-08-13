"""Pakize komut satırı arayüzü.

Bu modül ince bir kabuktur: girdiyi toplar, config'i bayraklarla ezer ve
`pipeline`'ı çağırır. Hiçbir iş mantığı burada yaşamaz.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import typer

from . import audio, book, runtime
from .config import (
    Config,
    config_path,
    load_config,
    set_config_value,
    write_default_config,
)
from .engines import EdgeEngine, EngineError, available_engines
from .models import SegmentType
from .pipeline import TranslationError, plan_speech, synthesize
from .sources import (
    ClipboardError,
    Roles,
    TranscriptError,
    collect,
    latest_session,
    read_clipboard,
)
from .translate import GoogleTranslator

app = typer.Typer(
    help="Metni ses dosyasına çevirir; kod bloklarını okumaz.",
    add_completion=False,
    no_args_is_help=True,
)

_SEGMENT_LABELS = {
    SegmentType.CODE_BLOCK: "kod bloğu",
    SegmentType.TABLE: "tablo",
    SegmentType.URL: "bağlantı",
    SegmentType.FILE_PATH: "dosya yolu",
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
    clipboard: bool = typer.Option(
        False, "--clipboard", "-c", help="Metni panodan al."
    ),
    transcript: bool = typer.Option(
        False,
        "--transcript",
        "-t",
        help="Metni bu dizinin Claude Code oturum kaydından al.",
    ),
    last: int = typer.Option(
        1,
        "--last",
        "-n",
        help="Transkriptten kaç söz sırası okunsun. 0 = tamamı.",
        min=0,
    ),
    roles: Roles = typer.Option(
        Roles.ASSISTANT.value,
        "--roles",
        help="Transkriptte hangi konuşmacılar okunsun.",
    ),
    session: Path = typer.Option(
        None,
        "--session",
        help="Belirli bir oturum kaydı dosyası (varsayılan: en yenisi).",
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
    translate: str = typer.Option(
        None,
        "--translate",
        "-T",
        help="Seslendirmeden önce bu dile çevir (örn. tr, en).",
    ),
    play: bool = typer.Option(
        True, "--play/--no-play", help="Ses hazır olunca otomatik çal."
    ),
    stream: bool = typer.Option(
        None,
        "--stream/--no-stream",
        help="Parçaları hazır oldukça çal; hepsinin bitmesini bekleme.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Ses üretmeden neyin okunacağını göster."
    ),
) -> None:
    """Bir metni seslendirir."""
    _first_run_hint()
    try:
        text = _read_source(
            source,
            clipboard=clipboard,
            transcript=transcript,
            last=last,
            roles=roles,
            session=session,
        )
    except (ClipboardError, TranscriptError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not text.strip():
        typer.secho(_bos_girdi_mesaji(clipboard, transcript), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    config = _resolved_config(
        voice=voice, rate=rate, engine=engine, stream=stream, translate_to=translate
    )

    if dry_run:
        _print_plan(text, config)
        return

    destination = output or _default_output_path(config)
    # Akıcı modda parçalar üretildikçe çalınır; sonda ikinci kez çalmayız.
    streaming = play and config.stream
    try:
        with _durdurulabilir(play):
            result = synthesize(
                text,
                destination,
                config,
                progress=_progress,
                on_part_ready=audio.play_async if streaming else None,
            )
    except KeyboardInterrupt:
        typer.secho("\nDurduruldu.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=130) from None
    except (EngineError, TranslationError) as exc:
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

    if play and not streaming:
        try:
            with _durdurulabilir(True):
                audio.play(result.output)
        except KeyboardInterrupt:
            typer.secho("\nDurduruldu.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=130) from None


@app.command("book")
def narrate_book(
    source: Path = typer.Argument(
        ...,
        help="Seslendirilecek kitap (.txt, .md, .epub, .pdf, .mobi ...).",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Bölümlerin yazılacağı dizin."
    ),
    voice: str = typer.Option(None, "--voice", "-v", help="TTS sesi."),
    rate: float = typer.Option(None, "--rate", "-r", help="Konuşma hızı çarpanı."),
    engine: str = typer.Option(None, "--engine", "-e", help="Kullanılacak motor."),
    translate: str = typer.Option(
        None,
        "--translate",
        "-T",
        help="Seslendirmeden önce bu dile çevir (örn. tr).",
    ),
    level: int = typer.Option(
        book.DEFAULT_HEADING_LEVEL,
        "--level",
        "-l",
        help="Bu seviyeye kadar başlıklar bölüm sayılır (1 = yalnızca '#').",
        min=1,
        max=6,
    ),
    force: bool = typer.Option(
        False, "--force", help="Var olan bölümleri de yeniden üret."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Ses üretmeden bölüm listesini göster."
    ),
) -> None:
    """Bir kitabı bölüm bölüm seslendirir.

    Var olan bölümler atlanır; yarıda kalan iş aynı komutla kaldığı yerden
    devam eder.
    """
    _first_run_hint()
    config = _resolved_config(
        voice=voice, rate=rate, engine=engine, translate_to=translate
    )
    destination = output or config.output_dir / book.slugify(source.stem)

    try:
        if dry_run:
            _print_chapters(source, level)
            return
        result = book.narrate(
            source, destination, config, level=level, force=force, progress=_chapter_progress
        )
    except book.BookError as exc:
        typer.secho(f"\nHata: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except (EngineError, TranslationError, audio.AudioError) as exc:
        typer.secho(f"\nHata: {exc}", fg=typer.colors.RED, err=True)
        typer.secho(
            "Üretilen bölümler korundu; aynı komutu tekrar çalıştırınca kaldığı "
            "yerden devam eder.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        typer.secho(
            "\nDurduruldu. Aynı komutla kaldığı yerden devam edebilirsin.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=130) from None

    typer.echo()
    if result.skipped:
        typer.secho(
            f"{result.skipped} bölüm zaten üretilmişti, atlandı.",
            fg=typer.colors.YELLOW,
        )
    typer.secho(
        f"Hazır: {len(result.chapters)} bölüm → {result.directory}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Oynatma listesi: {result.playlist}")


@app.command()
def pause() -> None:
    """Çalmakta olan seslendirmeyi duraklatır; duraklatılmışsa sürdürür.

    Tek komutun iki işi görmesi kasıtlı: klavye kısayolunda aynı tuşla hem
    durdurup hem devam edebilirsin.
    """
    pids = runtime.running_pids()
    if not pids:
        typer.secho("Çalan bir seslendirme yok.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    # Herhangi biri duraklatılmışsa hepsini sürdürürüz; aksi hâlde aynı tuşa
    # basmak bazılarını duraklatıp bazılarını sürdürerek karmaşa yaratırdı.
    if any(runtime.is_paused(pid) for pid in pids):
        etkilenen = sum(runtime.resume(pid) for pid in pids)
        _bildir(etkilenen, len(pids), "Devam ediyor", "Sürdürülecek bir çalma yok.")
        return

    etkilenen = sum(runtime.pause(pid) for pid in pids)
    _bildir(etkilenen, len(pids), "Duraklatıldı", "Duraklatılacak bir çalma yok.")


@app.command()
def stop() -> None:
    """Çalmakta olan seslendirmeyi durdurur."""
    pids = runtime.running_pids()
    if not pids:
        typer.secho("Çalan bir seslendirme yok.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    # Hepsi durdurulur: aynı anda birden çok ses çalıyorsa "durdur" demek
    # sesin kesilmesi demektir, birinin kesilmesi değil.
    etkilenen = sum(runtime.stop(pid) for pid in pids)
    _bildir(etkilenen, len(pids), "Durduruldu", "Seslendirme zaten sonlanmış.")


@app.command()
def replay(
    listele: bool = typer.Option(
        False, "--list", "-l", help="Çalmak yerine son üretilen sesleri listele."
    ),
    adet: int = typer.Option(10, "--count", "-n", help="Listelenecek kayıt sayısı."),
) -> None:
    """En son üretilen ses dosyasını yeniden çalar."""
    config = _resolved_config()
    kayitlar = _recent_outputs(config)

    if not kayitlar:
        typer.secho(
            f"{config.output_dir} içinde ses dosyası yok.", fg=typer.colors.YELLOW
        )
        raise typer.Exit(code=1)

    if listele:
        for path in kayitlar[:adet]:
            an = datetime.fromtimestamp(path.stat().st_mtime)
            typer.echo(f"{an:%Y-%m-%d %H:%M:%S}  {path}")
        return

    typer.echo(f"Çalınıyor: {kayitlar[0]}")
    try:
        # Buradan çalan ses de `pakize stop`/`pause` ile yönetilebilmeli.
        with _durdurulabilir(True):
            audio.play(kayitlar[0])
    except KeyboardInterrupt:
        typer.secho("Durduruldu.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=130) from None


@app.command()
def voices(
    language: str = typer.Option(
        None,
        "--language",
        "-l",
        help="Dil ön eki (örn. de, en-US); tümü için: all. Verilmezse özet görünüm.",
    ),
) -> None:
    """Edge motorunun sunduğu sesleri listeler."""
    import asyncio

    if language is not None:
        prefix = None if language.lower() == "all" else language
        found = asyncio.run(EdgeEngine.list_voices(prefix))
        if not found:
            typer.secho(f"{language} için ses bulunamadı.", fg=typer.colors.YELLOW)
            return
        _print_voices(found)
        typer.echo("")
        typer.echo(f"Seçmek için: pakize config set voice {found[0]['ShortName']}")
        return

    # Bayrak verilmediğinde tam döküm yerine özet: aktif sesin dili öne çıkar,
    # kalan 70+ dil tek satırlık başlıklarla listelenir; 300+ satır dökülmez.
    all_voices = asyncio.run(EdgeEngine.list_voices(None))
    active = load_config().voice
    lang_code = active.split("-")[0].lower()
    featured = [
        v for v in all_voices if v["Locale"].lower().startswith(lang_code + "-")
    ]
    others = [
        v for v in all_voices if not v["Locale"].lower().startswith(lang_code + "-")
    ]

    if featured:
        first = featured[0]
        language_name = first.get("LocaleName", first["Locale"]).split(" (")[0]
        typer.secho(f"── {language_name} (aktif ses: {active}) ──", bold=True)
        _print_voices(featured, active=active)
        typer.echo("")

    typer.secho("── Diğer diller (ayrıntı için: pakize voices -l de) ──", bold=True)
    for code, name, count in _language_summary(others):
        typer.echo(f"{code:<8} {name:<32} {count} ses")

    typer.echo("")
    typer.echo("Ses seçimi için sihirbaz: pakize setup")


def _print_voices(entries: list[dict], active: str | None = None) -> None:
    for entry in entries:
        marker = "  ← aktif" if entry["ShortName"] == active else ""
        typer.echo(
            f"{entry['ShortName']:<34} {entry['Gender']:<8} {entry['Locale']}{marker}"
        )


def _language_summary(entries: list[dict]) -> list[tuple[str, str, int]]:
    """Sesleri dile göre gruplar: (dil kodu, dil adı, ses sayısı) listesi.

    Dil adı servisin `LocaleName` alanından gelir ("German (Austria)" → "German");
    elle tutulan ikinci bir dil sözlüğü olmasın diye ülke kısmı atılır.
    """
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["Locale"].split("-")[0], []).append(entry)

    summary = []
    for code in sorted(groups):
        first = groups[code][0]
        name = first.get("LocaleName", first["Locale"]).split(" (")[0]
        summary.append((code, name, len(groups[code])))
    return summary


@app.command()
def setup() -> None:
    """Kurulum sihirbazı: dil ve ses seç, örneğini dinle, config'e yaz."""
    import asyncio

    try:
        all_voices = asyncio.run(EdgeEngine.list_voices(None))
    except Exception as exc:
        typer.secho(f"Ses listesi alınamadı: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    languages = {
        code: (name, count) for code, name, count in _language_summary(all_voices)
    }
    typer.secho("Diller:", bold=True)
    for code, (name, count) in languages.items():
        typer.echo(f"  {code:<8} {name:<32} {count} ses")

    lang = typer.prompt("\nDil kodu", default="tr").strip().lower()
    while lang not in languages:
        typer.secho(f"Tanınmayan dil kodu: {lang!r}", fg=typer.colors.YELLOW)
        lang = typer.prompt("Dil kodu", default="tr").strip().lower()

    candidates = [
        v for v in all_voices if v["Locale"].lower().startswith(lang + "-")
    ]
    typer.echo("")
    for number, entry in enumerate(candidates, start=1):
        typer.echo(f" {number:>2}) {entry['ShortName']:<34} {entry['Gender']}")

    typer.echo("\nNumara: örneği dinle • s+numara: seç (örn. s2) • q: çık")
    while True:
        choice = typer.prompt(">").strip().lower()
        if choice == "q":
            typer.echo("Bir şey yazılmadı.")
            return

        selecting = choice.startswith("s")
        try:
            number = int(choice[1:] if selecting else choice)
            voice_name = candidates[number - 1]["ShortName"]
        except (ValueError, IndexError):
            typer.secho(f"Geçersiz seçim: {choice!r}", fg=typer.colors.YELLOW)
            continue

        if not selecting:
            _play_sample(voice_name, lang)
            continue

        path = config_path()
        written = set_config_value("voice", voice_name, path)
        typer.secho(f"Yazıldı: voice = {written}", fg=typer.colors.GREEN)
        typer.echo(f"Config dosyası: {path}")
        if lang != "tr":
            typer.echo(
                "Başka dildeki metinleri bu dile çevirtmek istersen: "
                f"pakize config set translate_to {lang}"
            )
        return


_SAMPLE_TEXT_TR = (
    "Merhaba! Bu, seçtiğiniz sesin kısa bir örneği. "
    "Pakize metinlerinizi bu sesle okuyacak."
)
_SAMPLE_TEXT_EN = (
    "Hello! This is a short sample of the selected voice. "
    "Pakize will read your texts with this voice."
)


def _sample_text(lang: str) -> str:
    """Örnek cümleyi hedef dilde üretir.

    75 dillik elle çeviri sözlüğü tutmamak için mevcut çeviri katmanı
    kullanılır; servis çalışmazsa İngilizce yedek cümleye düşülür.
    """
    if lang == "tr":
        return _SAMPLE_TEXT_TR
    if lang == "en":
        return _SAMPLE_TEXT_EN
    try:
        return GoogleTranslator(target=lang).translate_lines([_SAMPLE_TEXT_TR])[0]
    except TranslationError:
        return _SAMPLE_TEXT_EN


def _play_sample(voice_name: str, lang: str) -> None:
    """Seçilen sesle kısa bir örnek üretip çalar.

    Örnek dosya kalıcı çıktı dizinine değil geçici bir klasöre yazılır; yoksa
    `pakize replay` listesinde örnek denemeler birikirdi.
    """
    import asyncio
    import tempfile

    typer.echo("Örnek hazırlanıyor...")
    with tempfile.TemporaryDirectory(prefix="pakize-ornek-") as tmp:
        target = Path(tmp) / "ornek.mp3"
        config = replace(load_config(), voice=voice_name)
        try:
            asyncio.run(EdgeEngine(config).synthesize(_sample_text(lang), target))
        except EngineError as exc:
            typer.secho(f"Örnek üretilemedi: {exc}", fg=typer.colors.YELLOW, err=True)
            return
        audio.play(target)


config_app = typer.Typer(invoke_without_command=True)
app.add_typer(
    config_app,
    name="config",
    help="Etkin ayarları gösterir; 'set' alt komutu ile değiştirir.",
)


@config_app.callback()
def show_config(
    ctx: typer.Context,
    init: bool = typer.Option(
        False,
        "--init",
        help="Varsayılan ayarlarla açıklamalı bir config dosyası oluştur.",
    ),
) -> None:
    """Etkin ayarları ve config dosyasının yolunu gösterir."""
    if ctx.invoked_subcommand is not None:
        return

    path = config_path()

    if init:
        try:
            yazilan = write_default_config(path)
        except FileExistsError:
            typer.secho(
                f"Dosya zaten var: {path}\n"
                "Üzerine yazmıyorum; değiştirmek istersen dosyayı elle düzenle.",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(code=1) from None
        typer.secho(f"Yazıldı: {yazilan}", fg=typer.colors.GREEN)
        return

    config = load_config(path)

    typer.echo(f"Config dosyası: {path}" + ("" if path.is_file() else " (yok)"))
    typer.echo(f"Motor          : {config.engine} (tanınanlar: {', '.join(available_engines())})")
    typer.echo(f"Yedek motor    : {config.fallback_engine or '—'}")
    typer.echo(f"Ses            : {config.voice}")
    typer.echo(f"Hız            : {config.rate} ({config.rate_percent()})")
    typer.echo(f"Parça sınırı   : {config.max_chunk_chars} karakter")
    typer.echo(f"Çıktı dizini   : {config.output_dir}")
    typer.echo(f"Akıcı çalma    : {'açık' if config.stream else 'kapalı'}")
    typer.echo(
        f"Ondalık düzelt : {'açık' if config.normalize_decimals else 'kapalı'}"
    )
    typer.echo("Politika:")
    for segment_type, action in sorted(config.policy.items(), key=lambda kv: kv[0].value):
        typer.echo(f"  {segment_type.value:<18} {action.value}")


@config_app.command("set")
def set_setting(
    key: str = typer.Argument(
        ..., metavar="AYAR", help="Ayar adı (örn. voice, rate, translate_to)."
    ),
    value: str = typer.Argument(..., metavar="DEĞER", help="Yazılacak yeni değer."),
) -> None:
    """Bir ayarı config dosyasına yazar; dosya yoksa oluşturur."""
    if key == "voice":
        _validate_voice(value)
    if key in ("engine", "fallback_engine") and value not in available_engines():
        typer.secho(
            f"Bilinmeyen motor: {value!r} (tanınanlar: {', '.join(available_engines())})",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    path = config_path()
    try:
        written = set_config_value(key, value, path)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    typer.secho(f"Yazıldı: {key} = {written}", fg=typer.colors.GREEN)
    typer.echo(f"Config dosyası: {path}")


def _validate_voice(name: str) -> None:
    """Ses adını edge'in listesine karşı doğrular.

    Liste ağdan gelir; ulaşılamazsa yazma engellenmez — çevrimdışıyken de
    ayar değiştirilebilmeli. Ad listede yoksa yazım hatasıdır, erken durdurulur.
    """
    import asyncio

    try:
        found = asyncio.run(EdgeEngine.list_voices(None))
    except Exception:
        typer.secho(
            "Uyarı: ses listesine ulaşılamadı, ad doğrulanmadan yazılıyor.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return

    if any(entry["ShortName"] == name for entry in found):
        return

    typer.secho(f"Ses bulunamadı: {name!r}", fg=typer.colors.RED, err=True)
    similar = [
        entry["ShortName"]
        for entry in found
        if entry["ShortName"].lower().startswith(name.lower()[:5])
    ]
    if similar:
        typer.echo("Benzer adlar: " + ", ".join(similar[:5]), err=True)
    typer.echo("Tüm liste için: pakize voices -l all", err=True)
    raise typer.Exit(code=1)


def _read_source(
    source: Path | None,
    clipboard: bool = False,
    transcript: bool = False,
    last: int = 1,
    roles: Roles = Roles.ASSISTANT,
    session: Path | None = None,
) -> str:
    """Metni kaynaklardan birinden okur; öncelik sırası buradaki sıradır."""
    if transcript or session is not None:
        kayit = session or latest_session(Path.cwd())
        # 0, "tamamı" demek; collect None bekliyor.
        return collect(kayit, last=last or None, roles=roles)
    if clipboard:
        return read_clipboard()
    if source is not None:
        return source.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        typer.secho(
            "Bir dosya yolu ver, --clipboard/--transcript kullan "
            "ya da metni stdin'den aktar.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    return sys.stdin.read()


def _first_run_hint() -> None:
    """Config dosyası henüz yoksa kurulum sihirbazını hatırlatır.

    Dosya oluşur oluşmaz susar; ilk kullanıcıyı bir kez yakalamak yeterli,
    her çalıştırmada tekrarlanan ipucu gürültü olurdu.
    """
    if config_path().is_file():
        return
    typer.secho(
        "İpucu: dil ve ses seçimi için 'pakize setup' (bir kez yeter).",
        fg=typer.colors.CYAN,
        err=True,
    )


def _bos_girdi_mesaji(clipboard: bool, transcript: bool) -> str:
    if transcript:
        return "Transkriptte okunacak bir konuşma bulunamadı."
    return "Pano boş." if clipboard else "Girdi boş."


def _resolved_config(
    voice: str | None = None,
    rate: float | None = None,
    engine: str | None = None,
    stream: bool | None = None,
    translate_to: str | None = None,
) -> Config:
    """Dosyadan gelen ayarları CLI bayraklarıyla ezer."""
    config = load_config()
    overrides = {
        key: value
        for key, value in (
            ("voice", voice),
            ("rate", rate),
            ("engine", engine),
            ("stream", stream),
            ("translate_to", translate_to),
        )
        if value is not None
    }
    return replace(config, **overrides) if overrides else config


def _default_output_path(config: Config) -> Path:
    """Çıktı verilmediğinde kullanılacak, zaman damgalı yol.

    Çalışma dizinini kirletmemek için config'teki çıktı dizinine yazarız.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return config.output_dir / f"{stamp}.mp3"


def _bildir(etkilenen: int, toplam: int, basari: str, bos_mesaj: str) -> None:
    """Kaç seslendirmenin etkilendiğini bildirir.

    Birden çok ses çalıyorsa sayıyı söylemek gerekir; tek sesse sayı gürültü
    olurdu.
    """
    if not etkilenen:
        typer.secho(bos_mesaj, fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    ek = f" ({etkilenen} seslendirme)" if toplam > 1 else ""
    typer.secho(f"{basari}.{ek}", fg=typer.colors.GREEN)


@contextlib.contextmanager
def _durdurulabilir(enabled: bool):
    """Çalma süresince süreci `pakize stop` ile durdurulabilir kılar.

    Sinyal geldiğinde önce çalan ses kesilir, sonra `KeyboardInterrupt`
    yükseltilir; böylece Ctrl+C ile `pakize stop` aynı yoldan ilerler ve
    arkada üretilmeye devam eden parçalar da iptal olur.
    """
    if not enabled:
        yield
        return

    def handler(signum, frame):
        audio.stop_playback()
        raise KeyboardInterrupt

    onceki = {sig: signal.signal(sig, handler) for sig in (signal.SIGTERM, signal.SIGINT)}
    runtime.register(os.getpid())
    try:
        yield
    finally:
        runtime.clear(os.getpid())
        for sig, eski in onceki.items():
            signal.signal(sig, eski)


def _chapter_progress(chapter: book.Chapter, total: int, skipped: bool) -> None:
    etiket = chapter.title or f"Bölüm {chapter.number}"
    durum = " (atlandı)" if skipped else ""
    typer.echo(f"Bölüm {chapter.number}/{total}: {etiket[:60]}{durum}")


def _print_chapters(source: Path, level: int) -> None:
    chapters = book.split_chapters(book.load_text(source), level)
    if not chapters:
        typer.secho("Bölüm bulunamadı.", fg=typer.colors.YELLOW)
        return

    toplam = f"{sum(len(chapter.text) for chapter in chapters):,}".replace(",", ".")
    typer.secho(
        f"{len(chapters)} bölüm, toplam {toplam} karakter.", fg=typer.colors.CYAN
    )
    for chapter in chapters:
        ad = chapter.filename(len(chapters))
        typer.echo(f"  {ad:<48} {len(chapter.text):>8} karakter")


def _recent_outputs(config: Config) -> list[Path]:
    """Çıktı dizinindeki ses dosyalarını en yeniden eskiye sıralar."""
    if not config.output_dir.is_dir():
        return []
    sesler = [
        path
        for path in config.output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in (".mp3", ".wav")
    ]
    return sorted(sesler, key=lambda p: p.stat().st_mtime, reverse=True)


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
