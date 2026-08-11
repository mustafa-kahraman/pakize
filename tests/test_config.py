"""Yapılandırma yükleme testleri."""

from pathlib import Path

import pytest

from pakize import platforms
from pakize.config import Config, load_config
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
