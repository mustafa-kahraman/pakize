"""Markdown blok ayrıştırıcısının testleri."""

from pakize.models import SegmentType
from pakize.parsing.markdown import parse_segments


def _types(text: str) -> list[SegmentType]:
    return [segment.type for segment in parse_segments(text)]


def test_cith_kod_blogu_dili_ile_taninir():
    segments = parse_segments("```python\nprint('merhaba')\nx = 1\n```")

    assert len(segments) == 1
    assert segments[0].type is SegmentType.CODE_BLOCK
    assert segments[0].language == "python"
    assert segments[0].line_count == 2
    assert segments[0].text == "print('merhaba')\nx = 1"


def test_dilsiz_kod_blogu():
    segments = parse_segments("```\nls -la\n```")

    assert segments[0].type is SegmentType.CODE_BLOCK
    assert segments[0].language is None


def test_kapanmayan_cit_dosya_sonuna_kadar_kod_sayilir():
    segments = parse_segments("Metin.\n\n```js\nconst a = 1;\nconst b = 2;")

    assert _types("Metin.\n\n```js\nconst a = 1;") == [
        SegmentType.PROSE,
        SegmentType.CODE_BLOCK,
    ]
    assert segments[1].line_count == 2


def test_tilde_cit_ve_ic_ice_backtick():
    segments = parse_segments("~~~\n```\nkod\n```\n~~~")

    assert len(segments) == 1
    assert segments[0].type is SegmentType.CODE_BLOCK
    assert segments[0].text == "```\nkod\n```"


def test_baslik_seviyesi_okunur():
    segments = parse_segments("## Kurulum ##")

    assert segments[0].type is SegmentType.HEADING
    assert segments[0].level == 2
    assert segments[0].text == "Kurulum"


def test_tablo_ayrac_satiriyla_taninir():
    text = "| Ad | Yaş |\n|----|-----|\n| Ali | 30 |\n| Ayşe | 25 |"
    segments = parse_segments(text)

    assert len(segments) == 1
    assert segments[0].type is SegmentType.TABLE
    assert segments[0].line_count == 2  # başlık ve ayraç satırı sayılmaz


def test_boru_karakteri_iceren_duz_metin_tablo_sayilmaz():
    assert _types("Bu bir | işareti içeren cümledir.") == [SegmentType.PROSE]


def test_liste_maddeleri_ayri_segmentlerdir():
    text = "- birinci madde\n- ikinci madde\n  devamı burada\n- üçüncü"
    segments = parse_segments(text)

    assert _types(text) == [SegmentType.LIST_ITEM] * 3
    assert segments[1].text == "ikinci madde devamı burada"


def test_numarali_liste():
    assert _types("1. adım\n2. adım") == [SegmentType.LIST_ITEM] * 2


def test_alinti_blogu_tek_segment():
    segments = parse_segments("> ilk satır\n> ikinci satır")

    assert len(segments) == 1
    assert segments[0].type is SegmentType.QUOTE
    assert segments[0].text == "ilk satır\nikinci satır"


def test_yatay_cizgi():
    assert _types("---") == [SegmentType.HORIZONTAL_RULE]
    assert _types("***") == [SegmentType.HORIZONTAL_RULE]


def test_girintili_kod_yalnizca_bos_satirdan_sonra():
    segments = parse_segments("Şöyle:\n\n    kod satiri\n    ikinci satir\n\nDevam.")

    assert [s.type for s in segments] == [
        SegmentType.PROSE,
        SegmentType.CODE_BLOCK,
        SegmentType.PROSE,
    ]


def test_liste_devam_satiri_kod_sayilmaz():
    text = "- madde\n    devam satiri"

    assert _types(text) == [SegmentType.LIST_ITEM]


def test_paragraf_yeni_blok_baslayinca_biter():
    text = "Bir cümle\nikinci satır\n# Başlık\ndevam"

    assert _types(text) == [
        SegmentType.PROSE,
        SegmentType.HEADING,
        SegmentType.PROSE,
    ]


def test_karma_belge_sirasi_korunur():
    text = (
        "# Başlık\n\n"
        "Giriş cümlesi.\n\n"
        "```py\nx = 1\n```\n\n"
        "- madde\n\n"
        "> alıntı\n"
    )

    assert _types(text) == [
        SegmentType.HEADING,
        SegmentType.PROSE,
        SegmentType.CODE_BLOCK,
        SegmentType.LIST_ITEM,
        SegmentType.QUOTE,
    ]


def test_bos_metin_segment_uretmez():
    assert parse_segments("") == []
    assert parse_segments("\n\n   \n") == []


def test_windows_satir_sonlari_desteklenir():
    assert _types("# Başlık\r\n\r\nMetin.") == [
        SegmentType.HEADING,
        SegmentType.PROSE,
    ]
