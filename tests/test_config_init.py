"""Üretilen varsayılan config dosyasının testleri."""

import pytest

from pakize.config import (
    Config,
    DEFAULT_POLICY,
    load_config,
    render_default_config,
    write_default_config,
)


def test_uretilen_dosya_varsayilanlarin_aynisini_verir(tmp_path):
    """En kritik davranış: dosya, kodun varsayılanlarından sapmamalı.

    Üretilen dosyayı geri okuduğumuzda hiçbir ayarın değişmemesi, iki ayrı
    doğruluk kaynağı oluşmadığının kanıtıdır.
    """
    path = tmp_path / "config.toml"
    write_default_config(path)

    assert load_config(path) == Config()


def test_her_segment_tipi_dosyada_yer_alir(tmp_path):
    path = tmp_path / "config.toml"
    write_default_config(path)

    icerik = path.read_text(encoding="utf-8")
    for segment_type in DEFAULT_POLICY:
        assert f"{segment_type.value} =" in icerik


def test_tanimsiz_ayarlar_yorum_olarak_yazilir():
    icerik = render_default_config()

    # Piper yolları varsayılanda tanımsız; TOML'da boş değer olmadığı için
    # örnek değerleriyle yorum satırı olarak dururlar.
    assert "# piper_model =" in icerik
    assert "# piper_binary =" in icerik


def test_tanimli_ayarlar_yorumlanmadan_yazilir():
    icerik = render_default_config()

    assert 'fallback_engine = "piper"' in icerik
    assert "# fallback_engine" not in icerik


def test_aciklamalar_degere_yapismaz():
    for satir in render_default_config().splitlines():
        if " #" not in satir or satir.lstrip().startswith("#"):
            continue
        deger, _, yorum = satir.partition("#")
        assert deger.endswith(" "), f"açıklama değere yapışmış: {satir!r}"


def test_mevcut_dosyanin_uzerine_yazilmaz(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('voice = "tr-TR-AhmetNeural"\n', encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_default_config(path)

    assert load_config(path).voice == "tr-TR-AhmetNeural"


def test_eksik_dizin_olusturulur(tmp_path):
    path = tmp_path / "yeni" / "dizin" / "config.toml"

    write_default_config(path)

    assert path.is_file()


def test_degistirilen_varsayilan_dosyaya_yansir(monkeypatch):
    """Varsayılan değişirse üretilen dosya kendiliğinden güncellenmeli."""
    import pakize.config as config_modulu

    monkeypatch.setattr(
        config_modulu, "Config", lambda: Config(voice="tr-TR-AhmetNeural", rate=1.3)
    )

    icerik = render_default_config()

    assert 'voice = "tr-TR-AhmetNeural"' in icerik
    assert "rate = 1.3" in icerik
