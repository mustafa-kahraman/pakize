"""CLI testleri.

Hermetiktir: gerçek TTS çağrısı ve ses çalma yamalanır, çıktı dizini geçici
klasöre yönlendirilir.
"""

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from pakize import cli
from pakize.config import Config

runner = CliRunner()

GERCEK_PLAY_TONE = cli._play_tone
"""Yamalanmadan önceki `_play_tone`; ton hatasını sınayan test geri takar."""


@pytest.fixture(autouse=True)
def tonlar(monkeypatch) -> list[str]:
    """İşaret seslerini çalmaz, adlarını kaydeder; gerçek ton üretimi ffmpeg ister."""
    kayit: list[str] = []
    monkeypatch.setattr(cli, "_play_tone", lambda name, config: kayit.append(name))
    return kayit


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

    sonuc = runner.invoke(cli.app, ["replay"])

    assert sonuc.exit_code == 0
    assert calinanlar == [yeni]


def test_son_listeleme_yeniden_eskiye_siralar(cikti_dizini, calinanlar):
    _ses_yaz(cikti_dizini, "eski.mp3", mtime=1_000)
    _ses_yaz(cikti_dizini, "yeni.mp3", mtime=2_000)

    sonuc = runner.invoke(cli.app, ["replay", "--list"])

    assert sonuc.exit_code == 0
    assert sonuc.stdout.index("yeni.mp3") < sonuc.stdout.index("eski.mp3")
    assert calinanlar == []


def test_son_ses_yoksa_anlamli_hata(cikti_dizini, calinanlar):
    sonuc = runner.invoke(cli.app, ["replay"])

    assert sonuc.exit_code == 1
    assert "ses dosyası yok" in sonuc.stdout
    assert calinanlar == []


def test_son_calarken_surec_kaydedilir(cikti_dizini, monkeypatch):
    """`son` ile çalan ses de `pakize dur`/`duraklat` ile yönetilebilmeli."""
    _ses_yaz(cikti_dizini, "kayit.mp3", mtime=2_000)
    kayitli: list[int | None] = []

    monkeypatch.setattr(cli.runtime, "_is_pakize", lambda pid: True)
    monkeypatch.setattr(
        cli.audio, "play", lambda path: kayitli.append(cli.runtime.running_pid())
    )

    sonuc = runner.invoke(cli.app, ["replay"])

    assert sonuc.exit_code == 0
    assert kayitli == [os.getpid()]
    assert cli.runtime.running_pid() is None


def test_son_ses_disi_dosyalari_yoksayar(cikti_dizini, calinanlar):
    _ses_yaz(cikti_dizini, "notlar.txt", mtime=3_000)
    ses = _ses_yaz(cikti_dizini, "kayit.mp3", mtime=2_000)

    sonuc = runner.invoke(cli.app, ["replay"])

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


def test_transcript_bayragi_oturum_kaydindan_okur(cikti_dizini, tmp_path, monkeypatch):
    import json

    kayit = tmp_path / "oturum.jsonl"
    kayit.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Transkriptten gelen cevap."}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "latest_session", lambda cwd: kayit)

    sonuc = runner.invoke(cli.app, ["speak", "--transcript", "--dry-run"])

    assert sonuc.exit_code == 0
    assert "Transkriptten gelen cevap." in sonuc.stdout


def test_transcript_bos_ise_anlamli_hata(cikti_dizini, tmp_path, monkeypatch):
    kayit = tmp_path / "bos.jsonl"
    kayit.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "latest_session", lambda cwd: kayit)

    sonuc = runner.invoke(cli.app, ["speak", "--transcript"])

    assert sonuc.exit_code == 1
    assert "okunacak bir konuşma bulunamadı" in sonuc.stderr


def test_oturum_kaydi_yoksa_hata_gosterilir(cikti_dizini, monkeypatch):
    def patla(cwd):
        raise cli.TranscriptError("oturum kaydı bulunamadı")

    monkeypatch.setattr(cli, "latest_session", patla)

    sonuc = runner.invoke(cli.app, ["speak", "--transcript"])

    assert sonuc.exit_code == 1
    assert "oturum kaydı bulunamadı" in sonuc.stderr


def test_dur_calan_sureci_sonlandirir(monkeypatch):
    durdurulan: list[int] = []
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [4242])
    monkeypatch.setattr(
        cli.runtime, "stop", lambda pid: bool(durdurulan.append(pid) or True)
    )

    sonuc = runner.invoke(cli.app, ["stop"])

    assert sonuc.exit_code == 0
    assert durdurulan == [4242]
    assert "Durduruldu." in sonuc.stdout


def test_dur_calan_yoksa_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [])

    sonuc = runner.invoke(cli.app, ["stop"])

    assert sonuc.exit_code == 1
    assert "Çalan bir seslendirme yok." in sonuc.stdout


def test_dur_surec_arada_olmusse_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [4242])
    monkeypatch.setattr(cli.runtime, "stop", lambda pid: False)

    sonuc = runner.invoke(cli.app, ["stop"])

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


# --- okuma kuyruğu -----------------------------------------------------------

ONDEKI_PID = 1111
"""Sırada bizden önce duran sahte sürecin numarası."""


@pytest.fixture
def kuyruk(cikti_dizini, monkeypatch):
    """Kayıttaki her süreci yaşıyor sayar; bekleme uykusunu kaydeder.

    `uykuda` listesine eklenen işlev ilk uykuda çağrılır: öndekinin kaydını
    düşürüp sıranın bize gelmesini canlandırır.
    """
    from pakize.pipeline import Plan, SpeechResult

    durum = {"uretilen": [], "uykular": 0, "ilk_uykuda": lambda: None}
    monkeypatch.setattr(cli.runtime, "_is_pakize", lambda pid: True)
    monkeypatch.setattr(cli.audio, "play", lambda path: None)

    def sahte_uyku(seconds):
        durum["uykular"] += 1
        if durum["uykular"] == 1:
            durum["ilk_uykuda"]()

    monkeypatch.setattr(cli.runtime.time, "sleep", sahte_uyku)

    def sahte_synthesize(text, destination, config, progress=None, on_part_ready=None):
        durum["uretilen"].append((text, cli.runtime.running_pids()))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"sahte-ses")
        return SpeechResult(output=destination, plan=Plan(), engine=config.engine)

    monkeypatch.setattr(cli, "synthesize", sahte_synthesize)
    return durum


def test_alindi_tonu_uretimden_once_calinir(kuyruk, tonlar, monkeypatch):
    sira: list[str] = []
    monkeypatch.setattr(cli, "_play_tone", lambda name, config: sira.append(name))
    gercek = cli.synthesize
    monkeypatch.setattr(
        cli, "synthesize", lambda *args, **kwargs: sira.append("synth") or gercek(*args, **kwargs)
    )

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert sira == ["accept", "synth"]


@pytest.mark.parametrize("bayrak", ["--no-play", "--dry-run"])
def test_calma_yokken_ton_calinmaz(kuyruk, tonlar, bayrak):
    sonuc = runner.invoke(cli.app, ["speak", bayrak], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert tonlar == []


@pytest.mark.parametrize(
    "bozuk",
    [
        pytest.param(("tone", cli.dictation.DictationError("ton üretilemedi")), id="ton"),
        pytest.param(("play", cli.audio.AudioError("ffplay yok")), id="calma"),
    ],
)
def test_ton_calinamazsa_uyarir_ve_okuma_surer(kuyruk, monkeypatch, bozuk):
    nerede, hata = bozuk

    def patla(*args):
        raise hata

    monkeypatch.setattr(cli, "_play_tone", GERCEK_PLAY_TONE)
    if nerede == "tone":
        monkeypatch.setattr(cli.dictation, "tone", patla)
    else:
        ton = Path("ton.wav")
        monkeypatch.setattr(cli.dictation, "tone", lambda name, config: ton)
        # Yalnızca ton patlasın; asıl ses çalınabilsin.
        monkeypatch.setattr(
            cli.audio, "play", lambda path: patla() if path == ton else None
        )

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert "İşaret sesi çalınamadı" in sonuc.stderr
    assert len(kuyruk["uretilen"]) == 1


def test_sira_gelmeden_uretim_baslamaz(kuyruk):
    cli.runtime.register(ONDEKI_PID, text="Başka bir metin.")
    kuyruk["ilk_uykuda"] = lambda: cli.runtime.clear(ONDEKI_PID)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert kuyruk["uykular"] == 1
    # Üretim başladığında öndeki gitmiş, sırada yalnız biz varız.
    assert kuyruk["uretilen"] == [("Merhaba.\n", [os.getpid()])]
    assert cli.runtime.running_pids() == []


def test_ayni_metin_siradaysa_basis_yok_sayilir(kuyruk, tonlar):
    cli.runtime.register(ONDEKI_PID, text="Merhaba.\n")

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert "yok sayıldı" in sonuc.stdout
    assert tonlar == ["duplicate"]
    assert kuyruk["uretilen"] == []
    assert kuyruk["uykular"] == 0
    # Öndeki kalır, bizim kaydımız düşer.
    assert cli.runtime.running_pids() == [ONDEKI_PID]


def test_farkli_metin_siraya_girer(kuyruk, tonlar):
    cli.runtime.register(ONDEKI_PID, text="Başka.\n")
    kuyruk["ilk_uykuda"] = lambda: cli.runtime.clear(ONDEKI_PID)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert tonlar == ["accept"]
    assert len(kuyruk["uretilen"]) == 1


def test_ayni_anda_basilan_tekrarda_ilk_kaydolan_kalir(kuyruk, tonlar, monkeypatch):
    """İki basış aynı damgayı alsa ve bizim pid küçük olsa da ilk kaydolan kalır."""
    monkeypatch.setattr(cli.runtime.time, "time_ns", lambda: 500)
    monkeypatch.setattr(cli.os, "getpid", lambda: ONDEKI_PID - 1)
    cli.runtime.register(ONDEKI_PID, text="Merhaba.\n")

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert tonlar == ["duplicate"]
    assert kuyruk["uretilen"] == []
    assert cli.runtime.running_pids() == [ONDEKI_PID]


def test_kayit_sirasinda_durdurulan_surec_130_ile_cikar_kayit_birakmaz(kuyruk, monkeypatch):
    def kes():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.runtime.time, "time_ns", kes)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 130
    assert "Durduruldu." in sonuc.stdout
    assert kuyruk["uretilen"] == []
    assert list(cli.runtime.state_dir().iterdir()) == []


def test_beklerken_durdurulan_surec_130_ile_cikar_kayit_birakmaz(kuyruk):
    cli.runtime.register(ONDEKI_PID, text="Başka.\n")

    def sinyal():
        raise KeyboardInterrupt

    kuyruk["ilk_uykuda"] = sinyal

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 130
    assert "Durduruldu." in sonuc.stdout
    assert kuyruk["uretilen"] == []
    assert cli.runtime.running_pids() == [ONDEKI_PID]


def test_replay_sirasini_bekler(cikti_dizini, kuyruk, monkeypatch):
    """Tekrar çalma da kuyruğa girer; iki Pakize üst üste çalmaz."""
    _ses_yaz(cikti_dizini, "kayit.mp3", mtime=2_000)
    cli.runtime.register(ONDEKI_PID, text="Başka.\n")
    kuyruk["ilk_uykuda"] = lambda: cli.runtime.clear(ONDEKI_PID)
    calarken: list[list[int]] = []
    monkeypatch.setattr(
        cli.audio, "play", lambda path: calarken.append(cli.runtime.running_pids())
    )

    sonuc = runner.invoke(cli.app, ["replay"])

    assert sonuc.exit_code == 0
    assert kuyruk["uykular"] == 1
    assert calarken == [[os.getpid()]]


def test_dur_bekleyenleri_de_durdurur(monkeypatch):
    """`stop` susturur: çalanla birlikte sırada bekleyenler de biter."""
    durdurulan: list[int] = []
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [ONDEKI_PID, 2222])
    monkeypatch.setattr(cli.runtime, "stop", lambda pid: bool(durdurulan.append(pid) or True))

    sonuc = runner.invoke(cli.app, ["stop"])

    assert sonuc.exit_code == 0
    assert durdurulan == [ONDEKI_PID, 2222]
    assert "Durduruldu. (2 seslendirme)" in sonuc.stdout


def test_dur_all_secenegi_yok():
    sonuc = runner.invoke(cli.app, ["stop", "--all"])

    assert sonuc.exit_code == 2
    assert "--all" in sonuc.output


def test_sonraki_yalniz_calani_keser(monkeypatch):
    """Sıranın başı kesilir; bekleyenlere dokunulmaz."""
    durdurulan: list[int] = []
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: 2222)
    monkeypatch.setattr(cli.runtime, "stop", lambda pid: bool(durdurulan.append(pid) or True))

    sonuc = runner.invoke(cli.app, ["skip"])

    assert sonuc.exit_code == 0
    assert durdurulan == [2222]
    assert sonuc.stdout.strip() == "Sonrakine geçildi."


def test_sonraki_calan_yoksa_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: None)

    sonuc = runner.invoke(cli.app, ["skip"])

    assert sonuc.exit_code == 1
    assert "Çalan bir seslendirme yok." in sonuc.stdout


def test_sonraki_surec_arada_olmusse_bilgi_verir(monkeypatch):
    monkeypatch.setattr(cli.runtime, "running_pid", lambda: 2222)
    monkeypatch.setattr(cli.runtime, "stop", lambda pid: False)

    sonuc = runner.invoke(cli.app, ["skip"])

    assert sonuc.exit_code == 1
    assert "zaten sonlanmış" in sonuc.stdout


def test_kayit_silinemezse_surec_temiz_cikar_ve_kalinti_canli_sayilmaz(kuyruk, monkeypatch):
    """Windows'ta başka sürecin okuduğu dosya silinemez; bu çıkışı kırmamalı."""
    kayit_dizini = cli.runtime.state_dir()
    gercek_unlink = Path.unlink

    def inatci_unlink(self, missing_ok=False):
        if self.parent == kayit_dizini:
            raise PermissionError(13, "Permission denied", str(self))
        return gercek_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", inatci_unlink)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 0
    assert len(kuyruk["uretilen"]) == 1
    # Kayıt ve kayıt kilidi yerinde kaldı...
    assert (kayit_dizini / str(os.getpid())).exists()
    assert (kayit_dizini / cli.runtime.REGISTRATION_LOCK_NAME).exists()
    # ...ama sahibi ölünce kayıt canlı sayılmaz, kimseyi bekletmez.
    monkeypatch.setattr(cli.runtime, "_is_pakize", lambda pid: False)
    assert cli.runtime.running_pids() == []
    assert cli.runtime.running_pid() is None


def test_duraklat_yalniz_calani_duraklatir_bekleyenler_bekler(monkeypatch):
    duraklatilan: list[int] = []
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [ONDEKI_PID, 2222])
    monkeypatch.setattr(cli.runtime, "is_paused", lambda pid: False)
    monkeypatch.setattr(
        cli.runtime, "pause", lambda pid: bool(duraklatilan.append(pid) or True)
    )

    sonuc = runner.invoke(cli.app, ["pause"])

    assert sonuc.exit_code == 0
    assert duraklatilan == [ONDEKI_PID]
    assert sonuc.stdout.strip() == "Duraklatıldı."


def test_config_init_dosya_olusturur(tmp_path, monkeypatch):
    hedef = tmp_path / "pakize" / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: hedef)

    sonuc = runner.invoke(cli.app, ["config", "--init"])

    assert sonuc.exit_code == 0
    assert hedef.is_file()
    assert str(hedef) in sonuc.stdout


def test_config_init_mevcut_dosyayi_ezmez(tmp_path, monkeypatch):
    hedef = tmp_path / "config.toml"
    hedef.write_text('voice = "tr-TR-AhmetNeural"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "config_path", lambda: hedef)

    sonuc = runner.invoke(cli.app, ["config", "--init"])

    assert sonuc.exit_code == 1
    assert "zaten var" in sonuc.stdout
    assert hedef.read_text(encoding="utf-8") == 'voice = "tr-TR-AhmetNeural"\n'


def test_config_komutu_etkin_ayarlari_gosterir(cikti_dizini):
    sonuc = runner.invoke(cli.app, ["config"])

    assert sonuc.exit_code == 0
    assert "tr-TR-EmelNeural" in sonuc.stdout
    assert str(cikti_dizini) in sonuc.stdout
    assert "Akıcı çalma" in sonuc.stdout


SAHTE_SESLER = [
    {
        "ShortName": "tr-TR-AhmetNeural",
        "Gender": "Male",
        "Locale": "tr-TR",
        "LocaleName": "Turkish (Turkey)",
    },
    {
        "ShortName": "tr-TR-EmelNeural",
        "Gender": "Female",
        "Locale": "tr-TR",
        "LocaleName": "Turkish (Turkey)",
    },
    {
        "ShortName": "de-AT-IngridNeural",
        "Gender": "Female",
        "Locale": "de-AT",
        "LocaleName": "German (Austria)",
    },
    {
        "ShortName": "de-DE-KatjaNeural",
        "Gender": "Female",
        "Locale": "de-DE",
        "LocaleName": "German (Germany)",
    },
    {
        "ShortName": "en-US-AriaNeural",
        "Gender": "Female",
        "Locale": "en-US",
        "LocaleName": "English (United States)",
    },
]


@pytest.fixture
def ses_listesi(monkeypatch):
    """`EdgeEngine.list_voices`'i ağa çıkmayan sabit bir listeye bağlar."""

    async def sahte(language=None):
        if language is None:
            return SAHTE_SESLER
        return [
            v
            for v in SAHTE_SESLER
            if v["ShortName"].lower().startswith(language.lower())
        ]

    monkeypatch.setattr(cli.EdgeEngine, "list_voices", staticmethod(sahte))


def test_voices_ozet_gorunumu_aktif_sesin_dilini_one_cikarir(
    ses_listesi, cikti_dizini
):
    sonuc = runner.invoke(cli.app, ["voices"])

    assert sonuc.exit_code == 0
    # Varsayılan ses Türkçe olduğundan üstte Türkçe blok görünür.
    assert "Turkish" in sonuc.stdout
    assert "aktif ses: tr-TR-EmelNeural" in sonuc.stdout
    assert "← aktif" in sonuc.stdout
    # Diğer diller tek satırlık özet olarak görünür; sesler dökülmez.
    assert "de-AT-IngridNeural" not in sonuc.stdout
    assert "German" in sonuc.stdout
    assert "2 ses" in sonuc.stdout
    assert "English" in sonuc.stdout
    assert "pakize setup" in sonuc.stdout


def test_voices_ozet_gorunumu_almanca_sese_uyar(ses_listesi, monkeypatch):
    """Aktif ses Almancaysa üstte Almanca sesler listelenir, Türkçe özete düşer."""
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda *args, **kwargs: replace(Config(), voice="de-AT-IngridNeural"),
    )

    sonuc = runner.invoke(cli.app, ["voices"])

    assert sonuc.exit_code == 0
    assert "aktif ses: de-AT-IngridNeural" in sonuc.stdout
    assert "de-DE-KatjaNeural" in sonuc.stdout
    assert "tr-TR-EmelNeural" not in sonuc.stdout
    assert "Turkish" in sonuc.stdout  # özet satırı


def test_voices_dil_filtresi_yalniz_o_dili_listeler(ses_listesi):
    sonuc = runner.invoke(cli.app, ["voices", "-l", "de"])

    assert sonuc.exit_code == 0
    assert "de-AT-IngridNeural" in sonuc.stdout
    assert "de-DE-KatjaNeural" in sonuc.stdout
    assert "tr-TR-EmelNeural" not in sonuc.stdout
    # Çıktı, kopyala-yapıştır bir sonraki adımla biter.
    assert "config set voice de-AT-IngridNeural" in sonuc.stdout


def test_voices_bilinmeyen_dil_anlamli_mesaj_verir(ses_listesi):
    sonuc = runner.invoke(cli.app, ["voices", "-l", "xx"])

    assert sonuc.exit_code == 0
    assert "ses bulunamadı" in sonuc.stdout


@pytest.fixture
def config_dosyasi(tmp_path, monkeypatch) -> Path:
    hedef = tmp_path / "pakize" / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: hedef)
    return hedef


def test_config_set_gecerli_sesi_yazar(ses_listesi, config_dosyasi):
    sonuc = runner.invoke(cli.app, ["config", "set", "voice", "de-AT-IngridNeural"])

    assert sonuc.exit_code == 0
    assert "Yazıldı" in sonuc.stdout
    assert 'voice = "de-AT-IngridNeural"' in config_dosyasi.read_text(encoding="utf-8")


def test_config_set_bilinmeyen_sesi_reddeder(ses_listesi, config_dosyasi):
    sonuc = runner.invoke(cli.app, ["config", "set", "voice", "de-AT-YokNeural"])

    assert sonuc.exit_code == 1
    assert "Ses bulunamadı" in sonuc.stderr
    assert "de-AT-IngridNeural" in sonuc.stderr  # benzer ad önerilir
    assert not config_dosyasi.exists()


def test_config_set_liste_alinamazsa_uyarir_ama_yazar(config_dosyasi, monkeypatch):
    """Çevrimdışıyken ayar değiştirme engellenmemeli; yalnızca uyarılmalı."""

    async def patla(language=None):
        raise ConnectionError("ağ yok")

    monkeypatch.setattr(cli.EdgeEngine, "list_voices", staticmethod(patla))

    sonuc = runner.invoke(cli.app, ["config", "set", "voice", "de-AT-IngridNeural"])

    assert sonuc.exit_code == 0
    assert "doğrulanmadan" in sonuc.stderr
    assert 'voice = "de-AT-IngridNeural"' in config_dosyasi.read_text(encoding="utf-8")


def test_config_set_ses_disi_ayarlari_da_yazar(config_dosyasi):
    sonuc = runner.invoke(cli.app, ["config", "set", "translate_to", "de"])

    assert sonuc.exit_code == 0
    assert 'translate_to = "de"' in config_dosyasi.read_text(encoding="utf-8")


def test_config_set_bilinmeyen_ayari_reddeder(config_dosyasi):
    sonuc = runner.invoke(cli.app, ["config", "set", "ses", "x"])

    assert sonuc.exit_code == 1
    assert "Bilinmeyen ayar" in sonuc.stderr
    assert not config_dosyasi.exists()


def test_config_set_bilinmeyen_motoru_reddeder(config_dosyasi):
    sonuc = runner.invoke(cli.app, ["config", "set", "engine", "yok"])

    assert sonuc.exit_code == 1
    assert "Bilinmeyen motor" in sonuc.stderr
    assert not config_dosyasi.exists()


def test_setup_dil_ve_ses_secip_yazar(ses_listesi, config_dosyasi):
    sonuc = runner.invoke(cli.app, ["setup"], input="de\ns1\n")

    assert sonuc.exit_code == 0
    assert "German" in sonuc.stdout  # dil özeti gösterildi
    assert "de-AT-IngridNeural" in sonuc.stdout  # numaralı liste
    assert 'voice = "de-AT-IngridNeural"' in config_dosyasi.read_text(encoding="utf-8")
    # Türkçe dışı seçimde çeviri ipucu verilir.
    assert "translate_to de" in sonuc.stdout


def test_setup_ornek_dinletir(ses_listesi, config_dosyasi, calinanlar, monkeypatch):
    """Numara girilince örnek çalınır, s+numara ile seçim yazılır."""

    async def sahte_synthesize(self, text, destination):
        destination.write_bytes(b"sahte-ornek")

    monkeypatch.setattr(cli.EdgeEngine, "synthesize", sahte_synthesize)
    monkeypatch.setattr(cli, "_sample_text", lambda dil: "Hallo")

    sonuc = runner.invoke(cli.app, ["setup"], input="de\n2\ns2\n")

    assert sonuc.exit_code == 0
    assert len(calinanlar) == 1
    assert 'voice = "de-DE-KatjaNeural"' in config_dosyasi.read_text(encoding="utf-8")


def test_setup_gecersiz_girdide_tekrar_sorar(ses_listesi, config_dosyasi):
    sonuc = runner.invoke(cli.app, ["setup"], input="xx\nde\nabc\ns99\ns1\n")

    assert sonuc.exit_code == 0
    assert "Tanınmayan dil kodu" in sonuc.stdout
    assert "Geçersiz seçim" in sonuc.stdout
    assert 'voice = "de-AT-IngridNeural"' in config_dosyasi.read_text(encoding="utf-8")


def test_setup_q_ile_yazmadan_cikar(ses_listesi, config_dosyasi):
    sonuc = runner.invoke(cli.app, ["setup"], input="de\nq\n")

    assert sonuc.exit_code == 0
    assert not config_dosyasi.exists()


def test_ilk_kurulum_ipucu_config_yokken_gosterilir(
    cikti_dizini, config_dosyasi, tmp_path
):
    kaynak = tmp_path / "metin.md"
    kaynak.write_text("Merhaba.\n", encoding="utf-8")

    sonuc = runner.invoke(cli.app, ["speak", str(kaynak), "--dry-run"])

    assert sonuc.exit_code == 0
    assert "pakize setup" in sonuc.stderr


def test_ilk_kurulum_ipucu_config_varsa_susar(cikti_dizini, config_dosyasi, tmp_path):
    config_dosyasi.parent.mkdir(parents=True, exist_ok=True)
    config_dosyasi.write_text("rate = 1.0\n", encoding="utf-8")
    kaynak = tmp_path / "metin.md"
    kaynak.write_text("Merhaba.\n", encoding="utf-8")

    sonuc = runner.invoke(cli.app, ["speak", str(kaynak), "--dry-run"])

    assert sonuc.exit_code == 0
    assert "pakize setup" not in sonuc.stderr


@pytest.fixture
def rate_limited(cikti_dizini, monkeypatch) -> list[Path]:
    """Çeviri kısıtlamasını taklit eder; çalınan uyarıları kaydeder."""
    from pakize.translate import TranslationRateLimited

    def limited_synthesize(text, destination, config, progress=None, on_part_ready=None):
        raise TranslationRateLimited("HTTP 429")

    played: list[Path] = []
    notice = Path("uyari.mp3")
    monkeypatch.setattr(cli, "synthesize", limited_synthesize)
    monkeypatch.setattr(cli.notices, "rate_limit_notice", lambda config: notice)
    monkeypatch.setattr(cli.audio, "play", played.append)
    monkeypatch.setattr(cli.runtime, "register", lambda pid, text=None: True)
    monkeypatch.setattr(cli.runtime, "clear", lambda pid: None)
    return played


def test_ceviri_kisitlaninca_uyari_sesi_calinir(rate_limited):
    sonuc = runner.invoke(cli.app, ["speak", "--translate", "tr"], input="Hello.\n")

    assert sonuc.exit_code == 1
    assert rate_limited == [Path("uyari.mp3")]


def test_calma_kapaliyken_uyari_sesi_calinmaz(rate_limited):
    sonuc = runner.invoke(
        cli.app, ["speak", "--translate", "tr", "--no-play"], input="Hello.\n"
    )

    assert sonuc.exit_code == 1
    assert rate_limited == []


def test_uyari_uretilemezse_asil_hata_yine_gosterilir(rate_limited, monkeypatch):
    from pakize.engines import EngineError

    def broken(config):
        raise EngineError("edge-tts yok")

    monkeypatch.setattr(cli.notices, "rate_limit_notice", broken)

    sonuc = runner.invoke(cli.app, ["speak", "--translate", "tr"], input="Hello.\n")

    assert sonuc.exit_code == 1
    assert "HTTP 429" in sonuc.output
    assert "Uyarı sesi çalınamadı" in sonuc.output


# --- dikte -------------------------------------------------------------------


@pytest.fixture
def dikte(monkeypatch):
    """Dikte akışını yamalar: kayıt yapılmaz, metin hazır kabul edilir."""
    state = {"text": "merhaba dünya", "outcome": cli.dictation.StopRequest.NONE,
             "delivered": [], "announced": [], "clipboard": []}

    def fake_dictate(config, deliver, status=None):
        deliver(state["text"])
        return state["text"]

    monkeypatch.setattr(cli.dictation, "request_stop", lambda: state["outcome"])
    monkeypatch.setattr(cli.dictation, "dictate", fake_dictate)
    monkeypatch.setattr(
        cli.dictation,
        "announce_error",
        lambda config, message: state["announced"].append(message),
    )
    monkeypatch.setattr(cli, "write_clipboard", state["clipboard"].append)
    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: Config())
    return state


def test_dikte_metni_ekrana_ve_panoya_yazar(dikte):
    sonuc = runner.invoke(cli.app, ["dictate"])

    assert sonuc.exit_code == 0
    assert "merhaba dünya" in sonuc.stdout
    assert dikte["clipboard"] == ["merhaba dünya"]


def test_dikte_pano_kapatilabilir(dikte):
    sonuc = runner.invoke(cli.app, ["dictate", "--no-clipboard"])

    assert sonuc.exit_code == 0
    assert dikte["clipboard"] == []


def test_ikinci_cagri_kaydi_bitirir(dikte):
    dikte["outcome"] = cli.dictation.StopRequest.REQUESTED

    sonuc = runner.invoke(cli.app, ["dictate"])

    assert sonuc.exit_code == 0
    assert "Kayıt bitiriliyor" in sonuc.stdout
    assert dikte["clipboard"] == []


def test_desifre_surerken_cagri_bilgi_verir(dikte):
    dikte["outcome"] = cli.dictation.StopRequest.ALREADY

    sonuc = runner.invoke(cli.app, ["dictate"])

    assert sonuc.exit_code == 0
    assert "deşifre sürüyor" in sonuc.stdout


def test_dikte_hatasi_sesle_bildirilir(dikte, monkeypatch):
    def failing(config, deliver, status=None):
        raise cli.dictation.DictationError("Kayıt boş: mikrofondan ses gelmedi.")

    monkeypatch.setattr(cli.dictation, "dictate", failing)

    sonuc = runner.invoke(cli.app, ["dictate"])

    assert sonuc.exit_code == 1
    assert "ses gelmedi" in sonuc.output
    assert dikte["announced"] == ["Kayıt boş: mikrofondan ses gelmedi."]


def test_pano_yazilamazsa_metin_yine_ekrandadir(dikte, monkeypatch):
    from pakize.sources import ClipboardError

    def broken(text):
        raise ClipboardError("xclip yok")

    monkeypatch.setattr(cli, "write_clipboard", broken)

    sonuc = runner.invoke(cli.app, ["dictate"])

    assert sonuc.exit_code == 1
    assert "merhaba dünya" in sonuc.stdout
    assert dikte["announced"] == ["xclip yok"]


# --- fix ---------------------------------------------------------------------


@pytest.fixture
def duzeltme_dosyasi(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: path)
    return path


def test_fix_tabloya_yazar(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["fix", "rümut", "remote"])

    assert sonuc.exit_code == 0
    assert "Yazıldı: rümut → remote" in sonuc.stdout
    assert '"rümut" = "remote"' in duzeltme_dosyasi.read_text(encoding="utf-8")


def test_fix_degisiklikte_eskisini_soyler(duzeltme_dosyasi):
    runner.invoke(cli.app, ["fix", "rümut", "remot"])

    sonuc = runner.invoke(cli.app, ["fix", "rümut", "remote"])

    assert sonuc.exit_code == 0
    assert "Değişti: rümut → remote (önce: remot)" in sonuc.stdout


def test_fix_list_tabloyu_gosterir(duzeltme_dosyasi):
    runner.invoke(cli.app, ["fix", "rümut", "remote"])

    sonuc = runner.invoke(cli.app, ["fix", "--list"])

    assert sonuc.exit_code == 0
    assert "rümut  →  remote" in sonuc.stdout


def test_fix_list_bos_tabloyu_soyler(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["fix", "--list"])

    assert sonuc.exit_code == 0
    assert "Düzeltme tablosu boş" in sonuc.stdout


def test_fix_remove_siler(duzeltme_dosyasi):
    runner.invoke(cli.app, ["fix", "rümut", "remote"])

    sonuc = runner.invoke(cli.app, ["fix", "--remove", "rümut"])

    assert sonuc.exit_code == 0
    assert "Silindi: rümut" in sonuc.stdout
    assert cli.load_config(duzeltme_dosyasi).asr_replacements == {}


def test_fix_remove_olmayani_soyler(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["fix", "--remove", "yok"])

    assert sonuc.exit_code == 1
    assert "Tabloda yok: yok" in sonuc.stdout


def test_fix_eksik_argumanla_kullanim_gosterir(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["fix", "rümut"])

    assert sonuc.exit_code == 1
    assert "Kullanım: pakize fix" in sonuc.output


def test_fix_okunus_sozlugune_dokunmaz(duzeltme_dosyasi):
    runner.invoke(cli.app, ["word", "Python", "paytın"])

    runner.invoke(cli.app, ["fix", "Python", "python"])
    runner.invoke(cli.app, ["fix", "--remove", "Python"])
    config = cli.load_config(duzeltme_dosyasi)

    assert config.tts_replacements == {"Python": "paytın"}
    assert config.asr_replacements == {}


# --- word --------------------------------------------------------------------


def test_word_okunus_sozlugune_yazar(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["word", "Python", "paytın"])

    assert sonuc.exit_code == 0
    assert "Yazıldı: Python → paytın" in sonuc.stdout
    metin = duzeltme_dosyasi.read_text(encoding="utf-8")
    assert "[tts_replacements]" in metin
    assert '"Python" = "paytın"' in metin
    assert cli.load_config(duzeltme_dosyasi).asr_replacements == {}


def test_word_degisiklikte_eskisini_soyler(duzeltme_dosyasi):
    runner.invoke(cli.app, ["word", "Python", "piton"])

    sonuc = runner.invoke(cli.app, ["word", "Python", "paytın"])

    assert sonuc.exit_code == 0
    assert "Değişti: Python → paytın (önce: piton)" in sonuc.stdout
    assert cli.load_config(duzeltme_dosyasi).tts_replacements == {"Python": "paytın"}


def test_word_list_sozlugu_gosterir(duzeltme_dosyasi):
    runner.invoke(cli.app, ["word", "Python", "paytın"])
    runner.invoke(cli.app, ["fix", "rümut", "remote"])

    sonuc = runner.invoke(cli.app, ["word", "-l"])

    assert sonuc.exit_code == 0
    assert "Python  →  paytın" in sonuc.stdout
    assert "rümut" not in sonuc.stdout


def test_word_list_bos_sozlugu_soyler(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["word", "--list"])

    assert sonuc.exit_code == 0
    assert "Okunuş sözlüğü boş." in sonuc.stdout


def test_word_remove_siler_duzeltme_tablosuna_dokunmaz(duzeltme_dosyasi):
    runner.invoke(cli.app, ["fix", "Python", "python"])
    runner.invoke(cli.app, ["word", "Python", "paytın"])

    sonuc = runner.invoke(cli.app, ["word", "--remove", "Python"])

    assert sonuc.exit_code == 0
    assert "Silindi: Python" in sonuc.stdout
    config = cli.load_config(duzeltme_dosyasi)
    assert config.tts_replacements == {}
    assert config.asr_replacements == {"Python": "python"}


def test_word_remove_olmayani_soyler(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["word", "--remove", "yok"])

    assert sonuc.exit_code == 1
    assert "Tabloda yok: yok" in sonuc.stdout


def test_word_eksik_argumanla_kullanim_gosterir(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["word", "Python"])

    assert sonuc.exit_code == 1
    assert (
        "Kullanım: pakize word KELİME OKUNUŞ  (örn. pakize word Python paytın)"
        in sonuc.output
    )


def test_word_argumansiz_kullanim_gosterir(duzeltme_dosyasi):
    sonuc = runner.invoke(cli.app, ["word"])

    assert sonuc.exit_code == 1
    assert "Kullanım: pakize word" in sonuc.output


def test_word_ile_yazilan_kelime_plan_speech_te_uygulanir(duzeltme_dosyasi):
    """Tam yol: komutla yaz, config'i yükle, planla; okunuş metne yansır."""
    from pakize.pipeline import plan_speech

    sonuc = runner.invoke(cli.app, ["word", "Python", "paytın"])
    assert sonuc.exit_code == 0

    config = cli.load_config(duzeltme_dosyasi)
    plan = plan_speech("Python güzeldir ama Pythonic kod zordur.", config)
    metin = "\n".join(chunk.text for chunk in plan.chunks)

    assert "paytın güzeldir" in metin
    assert "Pythonic kod" in metin


# --- bildirim yedeği ---------------------------------------------------------


@pytest.fixture
def bildirimler(monkeypatch) -> list[str]:
    kayit: list[str] = []
    monkeypatch.setattr(cli.desktop, "notify", kayit.append)
    return kayit


def test_ses_calinamazsa_bildirim_gosterilir(cikti_dizini, bildirimler, monkeypatch):
    def fake_synthesize(text, destination, config, progress=None, on_part_ready=None):
        raise cli.audio.AudioError("ffmpeg bulunamadı")

    monkeypatch.setattr(cli, "synthesize", fake_synthesize)

    sonuc = runner.invoke(cli.app, ["speak"], input="Merhaba.\n")

    assert sonuc.exit_code == 1
    assert bildirimler == ["Ses hatası: ffmpeg bulunamadı"]


def test_calma_kapaliyken_ses_hatasi_bildirilmez(cikti_dizini, bildirimler, monkeypatch):
    def fake_synthesize(text, destination, config, progress=None, on_part_ready=None):
        raise cli.audio.AudioError("ffmpeg bulunamadı")

    monkeypatch.setattr(cli, "synthesize", fake_synthesize)

    sonuc = runner.invoke(cli.app, ["speak", "--no-play"], input="Merhaba.\n")

    assert sonuc.exit_code == 1
    assert bildirimler == []


def test_sonda_calma_basarisizsa_bildirim_gosterilir(cikti_dizini, bildirimler, monkeypatch):
    def fake_synthesize(text, destination, config, progress=None, on_part_ready=None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp3")
        return SimpleNamespace(output=destination, plan=SimpleNamespace(skipped={}), engine=config.engine)

    def no_player(path):
        raise cli.audio.AudioError("ffplay bulunamadı")

    monkeypatch.setattr(cli, "synthesize", fake_synthesize)
    monkeypatch.setattr(cli.audio, "play", no_player)
    monkeypatch.setattr(cli.runtime, "register", lambda pid, text=None: True)
    monkeypatch.setattr(cli.runtime, "clear", lambda pid: None)

    sonuc = runner.invoke(cli.app, ["speak", "--no-stream"], input="Merhaba.\n")

    assert sonuc.exit_code == 1
    assert bildirimler == ["Ses hatası: ffplay bulunamadı"]


def test_uyari_sesi_calinamazsa_kisitlama_bildirilir(rate_limited, bildirimler, monkeypatch):
    def no_player(path):
        raise cli.audio.AudioError("ffplay bulunamadı")

    monkeypatch.setattr(cli.audio, "play", no_player)

    sonuc = runner.invoke(cli.app, ["speak", "--translate", "tr"], input="Hello.\n")

    assert sonuc.exit_code == 1
    assert len(bildirimler) == 1
    assert bildirimler[0].startswith("Çeviri şu an kullanılamıyor")
