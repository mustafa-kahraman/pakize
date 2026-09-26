"""Yapılandırma yükleme testleri."""

from pathlib import Path

import pytest

from pakize import platforms
from pakize.config import Config, load_config, render_default_config, set_config_value
from pakize.models import Action, SegmentType


def test_dosya_yoksa_varsayilanlar_kullanilir(tmp_path):
    config = load_config(tmp_path / "yok.toml")

    assert config == Config()


def test_skaler_ayarlar_ezilir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'voice = "tr-TR-AhmetNeural"\nrate = 1.3\nmax_chunk_chars = 900\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.voice == "tr-TR-AhmetNeural"
    assert config.rate == 1.3
    assert config.max_chunk_chars == 900


def test_cikti_dizini_varsayilani_gecici_dizin_altindadir():
    """Sabit `/tmp` değil: Windows'ta `%TEMP%`, macOS'ta oturuma özel klasör."""
    assert Config().output_dir == platforms.temp_root() / "pakize"


def test_cikti_dizini_ve_yollar_genisletilir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('output_dir = "~/sesler"\n', encoding="utf-8")

    config = load_config(path)

    assert config.output_dir == Path.home() / "sesler"


def test_mantiksal_ayarlar_okunur(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("stream = false\nnormalize_decimals = false\n", encoding="utf-8")

    config = load_config(path)

    assert config.stream is False
    assert config.normalize_decimals is False


def test_politika_varsayilanlarla_birlestirilir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[policy]\ncode_block = "skip"\n', encoding="utf-8")

    config = load_config(path)

    assert config.policy[SegmentType.CODE_BLOCK] is Action.SKIP
    # Belirtilmeyen tipler varsayılanını korur.
    assert config.policy[SegmentType.PROSE] is Action.READ
    assert config.policy[SegmentType.TABLE] is Action.ANNOUNCE


def test_bilinmeyen_segment_tipi_hata_verir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[policy]\nkod_blogu = "skip"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Bilinmeyen segment tipi"):
        load_config(path)


def test_bilinmeyen_eylem_hata_verir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[policy]\ncode_block = "oku"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="bilinmeyen eylem"):
        load_config(path)


@pytest.mark.parametrize(
    ("rate", "beklenen"),
    [(1.0, "+0%"), (1.15, "+15%"), (1.25, "+25%"), (0.9, "-10%"), (1.12, "+12%")],
)
def test_hiz_carpani_yuzdeye_cevrilir(rate, beklenen):
    assert Config(rate=rate).rate_percent() == beklenen


def test_perde_ve_ses_biciminde_isaret_bulunur():
    assert Config(pitch_hz=-5).pitch_spec() == "-5Hz"
    assert Config(volume=1.2).volume_percent() == "+20%"


def test_set_dosya_yoksa_varsayilanlarla_olusturur(tmp_path):
    path = tmp_path / "config.toml"

    yazilan = set_config_value("voice", "de-AT-IngridNeural", path)

    assert yazilan == '"de-AT-IngridNeural"'
    config = load_config(path)
    assert config.voice == "de-AT-IngridNeural"
    # Dosya varsayılan şablondan üretilir; diğer ayarlar aynı kalır.
    assert config.rate == Config().rate
    assert "[policy]" in path.read_text(encoding="utf-8")


def test_set_yalniz_ilgili_satiri_degistirir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '# benim notum\nvoice = "tr-TR-AhmetNeural"\nrate = 1.3\n', encoding="utf-8"
    )

    set_config_value("voice", "de-DE-KatjaNeural", path)

    icerik = path.read_text(encoding="utf-8")
    assert "# benim notum" in icerik
    assert "rate = 1.3" in icerik
    assert load_config(path).voice == "de-DE-KatjaNeural"


def test_set_yorumlu_ayari_etkinlestirir(tmp_path):
    """Üretilen dosyada `translate_to` yorum satırıdır; set onu etkinleştirir."""
    path = tmp_path / "config.toml"
    path.write_text(render_default_config(), encoding="utf-8")

    set_config_value("translate_to", "de", path)

    assert load_config(path).translate_to == "de"


def test_set_olmayan_anahtari_policy_tablosunu_bozmadan_ekler(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'voice = "tr-TR-EmelNeural"\n\n[policy]\ncode_block = "skip"\n',
        encoding="utf-8",
    )

    set_config_value("rate", "1.2", path)

    config = load_config(path)
    assert config.rate == 1.2
    # Yeni satır [policy] tablosunun içine düşmemeli.
    assert config.policy[SegmentType.CODE_BLOCK] is Action.SKIP


def test_set_sayi_ve_mantiksal_degerleri_tipiyle_yazar(tmp_path):
    path = tmp_path / "config.toml"

    set_config_value("stream", "false", path)
    set_config_value("max_chunk_chars", "900", path)

    config = load_config(path)
    assert config.stream is False
    assert config.max_chunk_chars == 900


def test_set_gecersiz_degeri_reddeder(tmp_path):
    path = tmp_path / "config.toml"

    with pytest.raises(ValueError, match="float bekleniyor"):
        set_config_value("rate", "hızlı", path)
    with pytest.raises(ValueError, match="true/false"):
        set_config_value("stream", "evet", path)
    with pytest.raises(ValueError, match="Bilinmeyen ayar"):
        set_config_value("ses", "x", path)

    # Hata durumunda dosya oluşturulmaz.
    assert not path.exists()


def test_set_yol_ayarini_dizgi_olarak_yazar(tmp_path):
    path = tmp_path / "config.toml"

    set_config_value("piper_model", "~/modeller/tr.onnx", path)

    # Okurken `~` genişletilir; dosyada verildiği gibi durur.
    assert load_config(path).piper_model == Path.home() / "modeller" / "tr.onnx"


def test_asr_baglami_serbest_metin_olarak_okunur(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'asr_context = """\nPakize\'yi uv ile kuruyorum.\nPiper var.\n"""\n',
        encoding="utf-8",
    )

    assert load_config(path).asr_context == "Pakize'yi uv ile kuruyorum.\nPiper var.\n"


def test_duzeltme_tablosu_okunur(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[asr_replacements]\n"Yuvı" = "uv"\n"Ecdi TTS" = "edge-tts"\n',
        encoding="utf-8",
    )

    assert load_config(path).asr_replacements == {"Yuvı": "uv", "Ecdi TTS": "edge-tts"}


def test_duzeltme_tablosunda_metin_olmayan_deger_reddedilir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[asr_replacements]\nuv = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="metin bekleniyor"):
        load_config(path)


def test_duzeltme_tablosunda_bos_anahtar_reddedilir(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[asr_replacements]\n"" = "uv"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="boş anahtar"):
        load_config(path)


def test_asr_baglami_set_ile_yazilir(tmp_path):
    path = tmp_path / "config.toml"

    set_config_value("asr_context", "Seslendirmede Piper var.", path)

    assert load_config(path).asr_context == "Seslendirmede Piper var."


def test_dikte_ayarlari_okunur(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        'dictate_microphone = "pulse:default"\n'
        "dictate_max_seconds = 120\n"
        'dictate_start_sound = "~/sesler/basla.mp3"\n'
        'dictate_error_sound = "~/sesler/hata.mp3"\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.dictate_microphone == "pulse:default"
    assert config.dictate_max_seconds == 120.0
    assert config.dictate_start_sound == Path("~/sesler/basla.mp3").expanduser()
    assert config.dictate_error_sound == Path("~/sesler/hata.mp3").expanduser()
    assert config.dictate_stop_sound is None


def test_dikte_varsayilanlari_ton_uretir_ve_bes_dakikada_keser():
    config = Config()

    assert config.dictate_microphone is None
    assert config.dictate_max_seconds == 300.0
    assert config.dictate_done_sound is None


# --- düzeltme tablosu: fix ---------------------------------------------------


def test_fix_dosya_yoksa_olusturur_ve_tabloya_yazar(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"

    assert set_replacement("rümut", "remote", path) is None
    assert load_config(path).asr_replacements == {"rümut": "remote"}
    assert load_config(path).voice == Config().voice


def test_fix_var_olan_tabloya_ekler_diger_satirlara_dokunmaz(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"
    original = (
        'voice = "tr-TR-AhmetNeural"\n\n[policy]\nurl = "skip"\n\n'
        '[asr_replacements]\n# yorum\n"Parkise" = "Pakize"\n'
    )
    path.write_text(original, encoding="utf-8")

    set_replacement("rümut", "remote", path)

    assert path.read_text(encoding="utf-8") == original + '"rümut" = "remote"\n'
    assert load_config(path).asr_replacements == {"Parkise": "Pakize", "rümut": "remote"}


def test_fix_tablo_yoksa_dosyanin_sonuna_acar(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"
    path.write_text('voice = "tr-TR-AhmetNeural"\n', encoding="utf-8")

    set_replacement("rümut", "remote", path)

    assert path.read_text(encoding="utf-8") == (
        'voice = "tr-TR-AhmetNeural"\n\n[asr_replacements]\n"rümut" = "remote"\n'
    )


def test_fix_ayni_anahtari_uzerine_yazar_ve_eskisini_doner(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"
    path.write_text('[asr_replacements]\n"rümut" = "remot"\n', encoding="utf-8")

    assert set_replacement("rümut", "remote", path) == "remot"
    assert load_config(path).asr_replacements == {"rümut": "remote"}


def test_fix_tablonun_ortasina_degil_sonuna_ekler(tmp_path):
    """Tablodan sonra başka bir tablo varsa satır yanlış tabloya düşmemeli."""
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"
    path.write_text(
        '[asr_replacements]\n"a" = "b"\n\n[policy]\nurl = "skip"\n', encoding="utf-8"
    )

    set_replacement("rümut", "remote", path)

    assert path.read_text(encoding="utf-8") == (
        '[asr_replacements]\n"a" = "b"\n"rümut" = "remote"\n\n[policy]\nurl = "skip"\n'
    )


def test_fix_ust_duzeydeki_ayni_adli_ayara_dokunmaz(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"
    path.write_text('voice = "x"\n[asr_replacements]\n', encoding="utf-8")

    set_replacement("voice", "ses", path)

    config = load_config(path)
    assert config.voice == "x"
    assert config.asr_replacements == {"voice": "ses"}


def test_fix_tirnak_iceren_degerleri_kacirir(tmp_path):
    from pakize.config import set_replacement

    path = tmp_path / "config.toml"

    set_replacement('de"mo', "README'yi", path)

    assert load_config(path).asr_replacements == {'de"mo': "README'yi"}


def test_fix_bos_yazimi_reddeder(tmp_path):
    from pakize.config import set_replacement

    with pytest.raises(ValueError):
        set_replacement(" ", "remote", tmp_path / "config.toml")
    with pytest.raises(ValueError):
        set_replacement("rümut", "", tmp_path / "config.toml")


def test_fix_remove_satiri_siler(tmp_path):
    from pakize.config import remove_replacement

    path = tmp_path / "config.toml"
    path.write_text(
        '[asr_replacements]\n"rümut" = "remote"\n"Riitmi" = "README"\n', encoding="utf-8"
    )

    assert remove_replacement("rümut", path) is True
    assert remove_replacement("rümut", path) is False
    assert load_config(path).asr_replacements == {"Riitmi": "README"}


def test_fix_remove_dosya_yoksa_false(tmp_path):
    from pakize.config import remove_replacement

    assert remove_replacement("x", tmp_path / "yok.toml") is False
