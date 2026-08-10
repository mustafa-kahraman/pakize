"""Claude Code transkript kaynağı testleri.

Hermetiktir: gerçek oturum kayıtlarına dokunulmaz, her test kendi geçici
`.jsonl` dosyasını yazar.
"""

import json
from pathlib import Path

import pytest

from pakize.sources import transcript
from pakize.sources.transcript import Roles, TranscriptError, Turn


def _yaz(path: Path, *records: dict) -> Path:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _user(text, **extra) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def _assistant(*blocks, **extra) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": list(blocks)},
        **extra,
    }


def _text(value: str) -> dict:
    return {"type": "text", "text": value}


@pytest.fixture
def kayit(tmp_path) -> Path:
    return tmp_path / "oturum.jsonl"


def test_asistan_metni_okunur(kayit):
    _yaz(kayit, _assistant(_text("Merhaba Mustafa.")))

    assert transcript.read_turns(kayit) == [Turn("assistant", "Merhaba Mustafa.")]


def test_dusunme_ve_arac_bloklari_atlanir(kayit):
    _yaz(
        kayit,
        _assistant(
            {"type": "thinking", "thinking": "içimden geçenler"},
            _text("Söylediğim şey."),
            {"type": "tool_use", "name": "Bash", "input": {}},
        ),
    )

    assert transcript.read_turns(kayit) == [Turn("assistant", "Söylediğim şey.")]


def test_arac_ciktilari_konusma_sayilmaz(kayit):
    _yaz(kayit, _user([{"type": "tool_result", "content": "komut çıktısı"}]))

    assert transcript.read_turns(kayit) == []


def test_alt_ajan_konusmalari_atlanir(kayit):
    _yaz(
        kayit,
        _assistant(_text("Ana konuşma.")),
        _assistant(_text("Alt ajan gevezeliği."), isSidechain=True),
    )

    assert transcript.read_turns(kayit) == [Turn("assistant", "Ana konuşma.")]


def test_ardisik_ayni_rol_tek_soz_sirasinda_birlesir(kayit):
    """Araç çağrılarıyla bölünen tek bir cevap, tek yanıt olarak okunmalı."""
    _yaz(
        kayit,
        _user("soru"),
        _assistant(_text("Önce şunu yapıyorum.")),
        _user([{"type": "tool_result", "content": "çıktı"}]),
        _assistant(_text("Sonra da bunu.")),
        _assistant(_text("Bitti.")),
    )

    turns = transcript.read_turns(kayit)

    assert turns == [
        Turn("user", "soru"),
        Turn("assistant", "Önce şunu yapıyorum.\n\nSonra da bunu.\n\nBitti."),
    ]


def test_kullanici_mesajindaki_arac_etiketleri_temizlenir(kayit):
    _yaz(
        kayit,
        _user(
            "<command-name>/goal</command-name>"
            "<command-args>hepsini tamamla</command-args>"
            "asıl söylediğim bu"
        ),
    )

    assert transcript.read_turns(kayit) == [Turn("user", "asıl söylediğim bu")]


def test_sistem_hatirlaticilari_temizlenir(kayit):
    _yaz(kayit, _user("gerçek mesaj <system-reminder>gürültü</system-reminder>"))

    assert transcript.read_turns(kayit) == [Turn("user", "gerçek mesaj")]


def test_bozuk_satirlar_atlanir(kayit):
    kayit.write_text(
        json.dumps(_assistant(_text("İyi satır."))) + "\n"
        "{yarım kalmış json\n"
        "\n",
        encoding="utf-8",
    )

    assert transcript.read_turns(kayit) == [Turn("assistant", "İyi satır.")]


def test_bos_metinli_kayitlar_soz_sirasi_uretmez(kayit):
    _yaz(kayit, _assistant(_text("   ")), _assistant({"type": "tool_use", "name": "x"}))

    assert transcript.read_turns(kayit) == []


def test_son_soz_sirasi_alinir(kayit):
    _yaz(
        kayit,
        _user("bir"),
        _assistant(_text("Birinci cevap.")),
        _user("iki"),
        _assistant(_text("İkinci cevap.")),
    )

    assert transcript.collect(kayit, last=1) == "İkinci cevap."


def test_birden_cok_soz_sirasi_alinir(kayit):
    _yaz(
        kayit,
        _user("bir"),
        _assistant(_text("Birinci cevap.")),
        _user("iki"),
        _assistant(_text("İkinci cevap.")),
    )

    assert transcript.collect(kayit, last=2) == "Birinci cevap.\n\nİkinci cevap."


def test_tamami_alinabilir(kayit):
    _yaz(kayit, _assistant(_text("Bir.")), _user("iki"), _assistant(_text("Üç.")))

    assert transcript.collect(kayit, last=None, roles=Roles.ALL).count(":") == 3


def test_yalnizca_kullanici_rolu(kayit):
    _yaz(kayit, _user("sorum"), _assistant(_text("cevabım")))

    assert transcript.collect(kayit, last=None, roles=Roles.USER) == "sorum"


def test_tum_roller_ayracla_okunur(kayit):
    _yaz(kayit, _user("sorum"), _assistant(_text("cevabım")))

    metin = transcript.collect(kayit, last=None, roles=Roles.ALL)

    assert metin == "Kullanıcı: sorum\n\nAsistan: cevabım"


def test_tek_rolde_ayrac_konmaz(kayit):
    _yaz(kayit, _assistant(_text("cevabım")))

    assert transcript.collect(kayit, last=None) == "cevabım"


def test_gecersiz_last_hata_verir(kayit):
    _yaz(kayit, _assistant(_text("bir şey")))

    with pytest.raises(ValueError):
        transcript.collect(kayit, last=0)


def test_bos_transkript_bos_dizge_doner(kayit):
    _yaz(kayit)

    assert transcript.collect(kayit) == ""


def test_dizin_adi_kodlamasi():
    kodlanan = transcript.session_dir(Path("/home/mustafa/Documents/projects/a.dev"))

    assert kodlanan.name == "-home-mustafa-Documents-projects-a-dev"


def test_oturumlar_yeniden_eskiye_siralanir(tmp_path, monkeypatch):
    import os

    proje = Path("/home/mustafa/proje")
    dizin = tmp_path / "-home-mustafa-proje"
    dizin.mkdir()
    monkeypatch.setattr(transcript, "TRANSCRIPT_ROOT", tmp_path)

    eski = _yaz(dizin / "eski.jsonl", _assistant(_text("a")))
    yeni = _yaz(dizin / "yeni.jsonl", _assistant(_text("b")))
    os.utime(eski, (1_000, 1_000))
    os.utime(yeni, (2_000, 2_000))

    assert transcript.find_sessions(proje) == [yeni, eski]
    assert transcript.latest_session(proje) == yeni


def test_oturum_yoksa_anlamli_hata(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript, "TRANSCRIPT_ROOT", tmp_path)

    with pytest.raises(TranscriptError, match="oturum kaydı bulunamadı"):
        transcript.latest_session(Path("/home/mustafa/olmayan"))
