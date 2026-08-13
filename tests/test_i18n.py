"""Arayüz dili testleri.

Katalog bütünlüğü elle değil mekanik olarak denetlenir: kaynaktaki her `_()`
çağrısının İngilizce karşılığı olmalı. Böylece yeni bir mesaj eklerken çeviriyi
unutmak testte yakalanır, kullanıcıda değil.
"""

import ast
from pathlib import Path
from dataclasses import replace
from string import Formatter

import pytest
from typer.testing import CliRunner

from pakize import cli, i18n
from pakize.cli import _SEGMENT_LABELS
from pakize.config import _FIELD_NOTES, _POLICY_NOTES

SRC = Path(__file__).resolve().parent.parent / "src" / "pakize"

runner = CliRunner()


@pytest.fixture(autouse=True)
def temiz_dil_ortami(monkeypatch):
    """Dil tespitini yalnızca testin kendi verdiği değişkenlere bağlar.

    `LC_ALL` ve `LC_MESSAGES`, `LANG`'i ezer. Bunlar makineden makineye dolu
    gelebildiği için (macOS koşucusunda `LC_ALL` doluydu) yalnızca `LANG` set
    eden bir test, ortama göre farklı sonuç verirdi.
    """
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)


def _wrapped_literals() -> set[str]:
    """Kaynak ağacındaki `_("...")` ve `in_language("...", ...)` metinleri."""
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("_", "in_language")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


def test_katalog_kaynaktaki_tum_metinleri_kapsar():
    eksik = _wrapped_literals() - set(i18n._EN)
    assert not eksik, f"İngilizce karşılığı olmayan metinler: {sorted(eksik)}"


def test_anons_sesin_diline_uyar():
    """Anons, arayüz dilinden değil `voice` alanının dilinden türer."""
    from pakize.config import Config
    from pakize.models import Action, Segment, SegmentType
    from pakize.parsing import apply_policy

    segment = Segment(type=SegmentType.CODE_BLOCK, text="x = 1", language="python")
    segment = replace(segment, line_count=12)
    politika = {**Config().policy, SegmentType.CODE_BLOCK: Action.ANNOUNCE}

    i18n.set_language("tr")  # arayüz Türkçe olsa bile ses ne diyorsa o
    ingilizce, _ = apply_policy(
        [segment], replace(Config(), voice="en-US-AndrewNeural", policy=politika)
    )
    turkce, _ = apply_policy(
        [segment], replace(Config(), voice="tr-TR-AhmetNeural", policy=politika)
    )

    assert ingilizce == ["There is a 12-line Python code block here."]
    assert turkce == ["Burada 12 satırlık bir Python kod bloğu var."]


def test_katalogda_olmayan_ses_dili_ingilizceye_duser():
    """Almanca ses: katalogda de yok, Türkçe cümle yerine İngilizce okunur."""
    from pakize.config import Config
    from pakize.models import Action, Segment, SegmentType
    from pakize.parsing import apply_policy

    segment = replace(
        Segment(type=SegmentType.TABLE, text="| a |"), line_count=3
    )
    politika = {**Config().policy, SegmentType.TABLE: Action.ANNOUNCE}

    sonuc, _ = apply_policy(
        [segment], replace(Config(), voice="de-AT-IngridNeural", policy=politika)
    )

    assert sonuc == ["There is a 3-line table here."]


def test_katalog_sozluk_uzerinden_gecen_metinleri_kapsar():
    """`_()` bazı yerlerde sözlük değeriyle çağrılır; AST taraması bunları görmez."""
    dolayli = (
        set(_FIELD_NOTES.values())
        | set(_POLICY_NOTES.values())
        | set(_SEGMENT_LABELS.values())
    )
    eksik = dolayli - set(i18n._EN)
    assert not eksik, f"İngilizce karşılığı olmayan sözlük değerleri: {sorted(eksik)}"


def test_ceviriler_ayni_yer_tutuculari_kullanir():
    """TR ve EN metinlerin format alanları birebir aynı olmalı.

    Alan adı uyuşmazsa `.format()` çalışma anında `KeyError` fırlatır; bu test
    o hatayı kullanıcıya gitmeden yakalar.
    """

    def alanlar(metin: str) -> set[str]:
        return {alan for _text, alan, _spec, _conv in Formatter().parse(metin) if alan}

    bozuk = {
        tr: (alanlar(tr), alanlar(en))
        for tr, en in i18n._EN.items()
        if alanlar(tr) != alanlar(en)
    }
    assert not bozuk, f"Yer tutucuları uyuşmayan çeviriler: {bozuk}"


def test_turkcede_metin_aynen_doner():
    i18n.set_language("tr")
    assert i18n._("Pano boş.") == "Pano boş."


def test_ingilizcede_cevrilir():
    i18n.set_language("en")
    assert i18n._("Pano boş.") == "The clipboard is empty."


def test_katalogda_olmayan_metin_turkceye_duser():
    i18n.set_language("en")
    assert i18n._("katalogda olmayan metin") == "katalogda olmayan metin"


def test_dil_config_dosyasindan_okunur(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    hedef = tmp_path / "pakize" / "config.toml"
    hedef.parent.mkdir(parents=True)
    hedef.write_text('ui_language = "en"\n', encoding="utf-8")

    i18n.set_language(None)

    assert i18n.language() == "en"


def test_dil_ortam_degiskeninden_okunur(tmp_path, monkeypatch):
    # Boş XDG dizini: gerçek config dosyası tespite karışmasın.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    i18n.set_language(None)
    assert i18n.language() == "tr"

    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    i18n.set_language(None)
    assert i18n.language() == "en"


def test_bozuk_config_dil_tespitini_kirmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    hedef = tmp_path / "pakize" / "config.toml"
    hedef.parent.mkdir(parents=True)
    hedef.write_text("bu toml değil [", encoding="utf-8")

    i18n.set_language(None)

    assert i18n.language() == "tr"


def test_ingilizce_arayuzde_komut_ciktisi_ingilizce(monkeypatch):
    i18n.set_language("en")
    monkeypatch.setattr(cli.runtime, "running_pids", lambda: [])

    sonuc = runner.invoke(cli.app, ["stop"])

    assert sonuc.exit_code == 1
    assert "No speech is playing." in sonuc.stdout
