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
