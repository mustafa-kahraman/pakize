"""CLI testleri.

Hermetiktir: gerçek TTS çağrısı ve ses çalma yamalanır, çıktı dizini geçici
klasöre yönlendirilir.
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pakize import cli
from pakize.config import Config

runner = CliRunner()


@pytest.fixture
def cikti_dizini(tmp_path, monkeypatch) -> Path:
    """`load_config`'i geçici bir çıktı dizinine bakacak şekilde yamalar."""
    hedef = tmp_path / "sesler"
    monkeypatch.setattr(
        cli, "load_config", lambda *args, **kwargs: replace(Config(), output_dir=hedef)
    )
    return hedef


@pytest.fixture
def calinanlar(monkeypatch) -> list[Path]:
    kayit: list[Path] = []
    monkeypatch.setattr(cli.audio, "play", lambda path: kayit.append(path))
    return kayit


def _ses_yaz(dizin: Path, ad: str, mtime: float) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    path = dizin / ad
    path.write_bytes(b"sahte-ses")
    import os

    os.utime(path, (mtime, mtime))
    return path


def test_son_en_yeni_dosyayi_calar(cikti_dizini, calinanlar):
    _ses_yaz(cikti_dizini, "eski.mp3", mtime=1_000)
    yeni = _ses_yaz(cikti_dizini, "yeni.mp3", mtime=2_000)

    sonuc = runner.invoke(cli.app, ["son"])

    assert sonuc.exit_code == 0
    assert calinanlar == [yeni]


def test_son_listeleme_yeniden_eskiye_siralar(cikti_dizini, calinanlar):
    _ses_yaz(cikti_dizini, "eski.mp3", mtime=1_000)
    _ses_yaz(cikti_dizini, "yeni.mp3", mtime=2_000)

    sonuc = runner.invoke(cli.app, ["son", "--list"])

    assert sonuc.exit_code == 0
    assert sonuc.stdout.index("yeni.mp3") < sonuc.stdout.index("eski.mp3")
    assert calinanlar == []


def test_son_ses_yoksa_anlamli_hata(cikti_dizini, calinanlar):
    sonuc = runner.invoke(cli.app, ["son"])

    assert sonuc.exit_code == 1
    assert "ses dosyası yok" in sonuc.stdout
    assert calinanlar == []


def test_son_ses_disi_dosyalari_yoksayar(cikti_dizini, calinanlar):
    _ses_yaz(cikti_dizini, "notlar.txt", mtime=3_000)
    ses = _ses_yaz(cikti_dizini, "kayit.mp3", mtime=2_000)

    sonuc = runner.invoke(cli.app, ["son"])

    assert sonuc.exit_code == 0
    assert calinanlar == [ses]


def test_dry_run_ses_uretmez(cikti_dizini, tmp_path):
    kaynak = tmp_path / "metin.md"
    kaynak.write_text("```py\nx = 1\n```\n\nMerhaba dünya.\n", encoding="utf-8")

    sonuc = runner.invoke(cli.app, ["speak", str(kaynak), "--dry-run"])

    assert sonuc.exit_code == 0
    assert "Merhaba dünya." in sonuc.stdout
    assert "x = 1" not in sonuc.stdout
    assert not cikti_dizini.exists()


def test_speak_varsayilan_cikti_dizinine_yazar(cikti_dizini, monkeypatch):
    from pakize.pipeline import Plan, SpeechResult

    yazilan: dict = {}

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        yazilan["hedef"] = destination
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)

    sonuc = runner.invoke(cli.app, ["speak", "--no-play"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert yazilan["hedef"].parent == cikti_dizini
    assert yazilan["hedef"].suffix == ".mp3"


def test_akici_mod_kapaliyken_ses_sonda_calinir(cikti_dizini, calinanlar, monkeypatch):
    from pakize.pipeline import Plan, SpeechResult

    gecen: dict = {}

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        gecen["on_part_ready"] = on_part_ready
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert gecen["on_part_ready"] is None
    assert len(calinanlar) == 1


def test_akici_modda_ses_parcalar_uzerinden_calinir(
    cikti_dizini, calinanlar, monkeypatch
):
    from pakize.pipeline import Plan, SpeechResult

    gecen: dict = {}

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        gecen["on_part_ready"] = on_part_ready
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)

    sonuc = runner.invoke(cli.app, ["speak", "--stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert gecen["on_part_ready"] is cli.audio.play_async
    # Akıcı modda sonda ikinci kez çalınmaz.
    assert calinanlar == []


def test_clipboard_bayragi_panodan_okur(cikti_dizini, monkeypatch):
    monkeypatch.setattr(cli, "read_clipboard", lambda: "Panodaki metin.")

    sonuc = runner.invoke(cli.app, ["speak", "--clipboard", "--dry-run"])

    assert sonuc.exit_code == 0
    assert "Panodaki metin." in sonuc.stdout


def test_bos_pano_anlamli_hata_verir(cikti_dizini, monkeypatch):
    monkeypatch.setattr(cli, "read_clipboard", lambda: "   \n")

    sonuc = runner.invoke(cli.app, ["speak", "--clipboard"])

    assert sonuc.exit_code == 1
    assert "Pano boş." in sonuc.stderr


def test_pano_araci_yoksa_hata_gosterilir(cikti_dizini, monkeypatch):
    def patla():
        raise cli.ClipboardError("Pano okunamıyor: xclip kurulu değil.")

    monkeypatch.setattr(cli, "read_clipboard", patla)

    sonuc = runner.invoke(cli.app, ["speak", "--clipboard"])

    assert sonuc.exit_code == 1
    assert "xclip kurulu değil" in sonuc.stderr


def test_dur_calan_sureci_sonlandirir(monkeypatch):
    durdurulan: list[int] = []
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: 4242)
    monkeypatch.setattr(
        cli.runtime, "stop", lambda pid: bool(durdurulan.append(pid) or True)
    )

    sonuc = runner.invoke(cli.app, ["dur"])

    assert sonuc.exit_code == 0
    assert durdurulan == [4242]
    assert "Durduruldu." in sonuc.stdout


def test_dur_calan_yoksa_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: None)

    sonuc = runner.invoke(cli.app, ["dur"])

    assert sonuc.exit_code == 1
    assert "Çalan bir seslendirme yok." in sonuc.stdout


def test_dur_surec_arada_olmusse_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: 4242)
    monkeypatch.setattr(cli.runtime, "stop", lambda pid: False)

    sonuc = runner.invoke(cli.app, ["dur"])

    assert sonuc.exit_code == 1
    assert "zaten sonlanmış" in sonuc.stdout


def test_calma_sirasinda_surec_kaydedilir(cikti_dizini, monkeypatch):
    from pakize.pipeline import Plan, SpeechResult

    kayitli: list[int | None] = []

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        kayitli.append(cli.runtime.running_pid())
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)
    monkeypatch.setattr(cli.runtime, "_is_pakize", lambda pid: True)
    monkeypatch.setattr(cli.audio, "play", lambda path: None)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert kayitli == [os.getpid()]
    # Çalma bitince kayıt düşer.
    assert cli.runtime.running_pid() is None


def test_calma_kapaliyken_surec_kaydedilmez(cikti_dizini, monkeypatch):
    from pakize.pipeline import Plan, SpeechResult

    kayitli: list[int | None] = []

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        kayitli.append(cli.runtime.running_pid())
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)
    monkeypatch.setattr(cli.runtime, "_is_pakize", lambda pid: True)

    sonuc = runner.invoke(cli.app, ["speak", "--no-play"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert kayitli == [None]


def test_config_komutu_etkin_ayarlari_gosterir(cikti_dizini):
    sonuc = runner.invoke(cli.app, ["config"])

    assert sonuc.exit_code == 0
    assert "tr-TR-EmelNeural" in sonuc.stdout
    assert str(cikti_dizini) in sonuc.stdout
    assert "Akıcı çalma" in sonuc.stdout
