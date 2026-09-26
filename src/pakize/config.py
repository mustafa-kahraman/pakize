"""Pakize yapılandırması.

Ayarlar üç katmandan gelir; sonraki öncekini ezer:
1. Buradaki varsayılanlar
2. `~/.config/pakize/config.toml`
3. CLI bayrakları

Segment politikası da config'te yaşar; böylece "kodu atla" davranışı koda
gömülü bir kural değil, kullanıcının değiştirebildiği bir tercih olur.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from .i18n import _
from .models import Action, SegmentType
from .platforms import config_home, temp_root

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


DEFAULT_POLICY: dict[SegmentType, Action] = {
    SegmentType.PROSE: Action.READ,
    SegmentType.HEADING: Action.READ,
    SegmentType.LIST_ITEM: Action.READ,
    SegmentType.QUOTE: Action.READ,
    SegmentType.INLINE_CODE: Action.READ,
    SegmentType.CODE_BLOCK: Action.ANNOUNCE,
    SegmentType.TABLE: Action.ANNOUNCE,
    SegmentType.URL: Action.SKIP,
    SegmentType.FILE_PATH: Action.READ,
    SegmentType.HORIZONTAL_RULE: Action.SKIP,
}

DEFAULT_OUTPUT_DIR = temp_root() / "pakize"
"""Çıktı yolu verilmediğinde seslerin yazıldığı dizin.

Sistemin geçici dizini altındadır: Linux'ta `/tmp/pakize`, Windows'ta
`%TEMP%\\pakize`. Kalıcı arşiv isteyen `output_dir` ayarını değiştirir.
"""


@dataclass(frozen=True)
class Config:
    """Tek bir seslendirme çalışmasının tüm ayarları."""

    voice: str = "tr-TR-EmelNeural"
    engine: str = "edge"
    """Birincil motor: "edge" veya "piper"."""

    fallback_engine: str | None = "piper"
    """Birincil motor başarısız olursa denenecek motor; None ise yedek yok."""

    rate: float = 1.15
    """Konuşma hızı çarpanı. 1.0 = normal. Ondalıklı değer serbesttir."""

    pitch_hz: int = 0
    """Ses perdesi kaydırması (Hz). 0 = değişiklik yok."""

    volume: float = 1.0
    """Ses yüksekliği çarpanı. 1.0 = normal."""

    max_chunk_chars: int = 2500
    """Bir TTS isteğine sığdırılacak azami karakter sayısı."""

    output_dir: Path = DEFAULT_OUTPUT_DIR
    """Çıktı yolu verilmediğinde seslerin biriktiği dizin."""

    normalize_decimals: bool = True
    """Ondalık sayılardaki noktayı virgüle çevir (Türkçe okunuş için)."""

    ui_language: str = ""
    """Arayüz dili ("tr"/"en"); boşsa sistem dilinden tespit edilir."""

    translate_to: str | None = None
    """Seslendirmeden önce çevrilecek hedef dil kodu; None ise çeviri yok."""

    translate_from: str = "auto"
    """Kaynak dil kodu; "auto" ise servis kendisi tespit eder."""

    stream: bool = True
    """Parçalar hazır oldukça sırayla çal; hepsinin bitmesini bekleme."""

    policy: dict[SegmentType, Action] = field(
        default_factory=lambda: dict(DEFAULT_POLICY)
    )

    piper_model: Path | None = None
    """Piper ses modelinin (.onnx) yolu; None ise Piper motoru kullanılamaz."""

    piper_binary: Path | None = None
    """Piper çalıştırılabilirinin yolu; None ise PATH üzerinden aranır."""

    asr_engine: str = "qwen"
    """Konuşmayı metne çeviren motor."""

    asr_server_url: str | None = None
    """Dışarıda çalışan deşifre sunucusunun adresi.

    Doluysa Pakize bu sunucuyu kullanır ve ona dokunmaz. Boşsa ve `asr_model`
    tanımlıysa Pakize sunucuyu her iş için kendisi başlatıp kapatır.
    """

    asr_model: Path | None = None
    """Pakize'nin başlatacağı sunucu için model dosyasının (.gguf) yolu."""

    asr_mmproj: Path | None = None
    """Modelin ses kodlayıcısının (mmproj .gguf) yolu; `asr_model` ile gerekir."""

    asr_server_binary: Path | None = None
    """`llama-server` çalıştırılabilirinin yolu; None ise PATH üzerinden aranır."""

    asr_context: str | None = None
    """Tanımaya arka plan bilgisi veren serbest metin; None ise bağlam yok.

    Terimleri cümle içinde anlatan bir paragraf olmalı: Türkçede çıplak kelime
    listesi tanımayı ölçülebilir biçimde değiştirmiyor, terimi kullanım
    yeriyle anlatan cümle değiştiriyor.
    """

    asr_replacements: dict[str, str] = field(default_factory=dict)
    """Deşifre çıktısına uygulanan düzeltme tablosu: yanlış yazım → doğrusu.

    Bağlamla bile tutmayan kelimeler için (`uv`, `EPUB` gibi). Model devreye
    girmez; aynı çıktı her seferinde aynı biçimde düzelir.
    """

    asr_timeout: float = 300.0
    """Bir deşifre isteğinin azami süresi (saniye).

    Deşifre uzun sürebilir: uzun kayıtlarda gerçek zamanın birkaç katı.
    Cömert bir üst sınır, yarıda kesilmiş bir kayıttan iyidir.
    """

    dictate_microphone: str | None = None
    """Diktede kayıt yapılacak mikrofon, ffmpeg'in `biçim:aygıt` yazımıyla.

    None ise platformun varsayılan aygıtı kullanılır (Linux'ta `pulse:default`,
    macOS'ta `avfoundation::0`). Windows'ta varsayılan yoktur; `dshow:audio=Ad`
    biçiminde yazılması gerekir.
    """

    dictate_max_seconds: float = 300.0
    """Bir diktenin azami kayıt süresi (saniye); emniyet supabı.

    İkinci basış unutulursa mikrofon sonsuza dek açık kalmaz: süre dolunca
    kayıt kendiliğinden biter ve o ana kadarki konuşma deşifre edilir.
    """

    dictate_start_sound: Path | None = None
    """Kayıt başlarken çalınacak ses dosyası; None ise üretilen ton."""

    dictate_stop_sound: Path | None = None
    """Kayıt bitince çalınacak ses dosyası; None ise üretilen ton."""

    dictate_done_sound: Path | None = None
    """Metin panoya konunca çalınacak ses dosyası; None ise üretilen ton."""

    dictate_error_sound: Path | None = None
    """Dikte başarısız olunca çalınacak ses dosyası; None ise üretilen ton."""

    def rate_percent(self) -> str:
        """Hız çarpanını edge-tts'in beklediği `+15%` biçimine çevirir.

        edge-tts ara değerleri kabul ettiği için 1.15 gibi kademe dışı
        hızlar da sorunsuz çalışır; yalnızca tam sayı yüzdeye yuvarlarız.
        """
        return _signed_percent(self.rate)

    def volume_percent(self) -> str:
        return _signed_percent(self.volume)

    def pitch_spec(self) -> str:
        return f"{self.pitch_hz:+d}Hz"


def _signed_percent(multiplier: float) -> str:
    """1.15 → "+15%", 0.9 → "-10%", 1.0 → "+0%"."""
    return f"{round((multiplier - 1.0) * 100):+d}%"


def config_path() -> Path:
    """Kullanıcı config dosyasının yolu.

    Linux ve macOS'ta `~/.config/pakize/config.toml`, Windows'ta
    `%APPDATA%\\pakize\\config.toml`; `XDG_CONFIG_HOME` her üçünde de önceliklidir.
    """
    return config_home() / "pakize" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Config dosyasını okuyup varsayılanların üzerine uygular.

    Dosya yoksa varsayılanlar döner — Pakize kurulum gerektirmeden çalışır.
    """
    target = path or config_path()
    if not target.is_file():
        return Config()

    with target.open("rb") as handle:
        data = tomllib.load(handle)

    return _apply_overrides(Config(), data)


_SCALAR_FIELDS: dict[str, type] = {
    "voice": str,
    "engine": str,
    "fallback_engine": str,
    "rate": float,
    "pitch_hz": int,
    "volume": float,
    "max_chunk_chars": int,
    "normalize_decimals": bool,
    "ui_language": str,
    "stream": bool,
    "translate_to": str,
    "translate_from": str,
    "asr_engine": str,
    "asr_server_url": str,
    "asr_context": str,
    "asr_timeout": float,
    "dictate_microphone": str,
    "dictate_max_seconds": float,
}
"""Config dosyasında tanınan düz ayarlar ve tipleri."""

_PATH_FIELDS = (
    "piper_model",
    "piper_binary",
    "output_dir",
    "asr_model",
    "asr_mmproj",
    "asr_server_binary",
    "dictate_start_sound",
    "dictate_stop_sound",
    "dictate_done_sound",
    "dictate_error_sound",
)
"""Dosya yolu tutan ayarlar; okunurken `~` genişletilir."""


def _apply_overrides(base: Config, data: dict) -> Config:
    """TOML sözlüğündeki tanınan anahtarları Config üzerine uygular."""
    overrides: dict = {}
    for key, caster in _SCALAR_FIELDS.items():
        if key in data and data[key] is not None:
            overrides[key] = caster(data[key])

    for key in _PATH_FIELDS:
        if data.get(key):
            overrides[key] = Path(str(data[key])).expanduser()

    policy_table = data.get("policy")
    if isinstance(policy_table, dict):
        overrides["policy"] = _merge_policy(base.policy, policy_table)

    replacements_table = data.get("asr_replacements")
    if isinstance(replacements_table, dict):
        overrides["asr_replacements"] = _read_replacements(replacements_table)

    return replace(base, **overrides)


_FIELD_NOTES: dict[str, str] = {
    "voice": "kullanılacak ses — 'pakize voices' ile listele",
    "engine": "birincil TTS motoru",
    "fallback_engine": "birincil motor çalışmazsa denenecek motor",
    "rate": "konuşma hızı çarpanı; 1.0 = normal, ara değerler serbest (1.12 olur)",
    "volume": "ses yüksekliği çarpanı",
    "pitch_hz": "ses perdesi kaydırması (Hz)",
    "max_chunk_chars": "bir TTS isteğine sığdırılacak azami karakter",
    "output_dir": "çıktı yolu verilmediğinde seslerin biriktiği dizin",
    "stream": "ilk parça hazır olunca çalmaya başla, hepsini bekleme",
    "normalize_decimals": "1.15 → 1,15 (Türkçe'de ondalık ayracı virgüldür)",
    "ui_language": "arayüz dili (tr/en); boşsa sistem dilinden tespit edilir",
    "translate_to": "seslendirmeden önce çevrilecek dil (örn. tr); boşsa çeviri yok",
    "translate_from": "kaynak dil; auto ise servis kendisi tespit eder",
    "piper_model": "Piper ses modelinin (.onnx) yolu",
    "piper_binary": "piper çalıştırılabiliri; boşsa PATH'te aranır",
    "asr_engine": "konuşmayı metne çeviren motor",
    "asr_server_url": "dışarıda çalışan deşifre sunucusu; boşsa asr_model ile Pakize başlatır",
    "asr_model": "deşifre modeli (.gguf); sunucu her iş için açılıp kapanır",
    "asr_mmproj": "modelin ses kodlayıcısı (mmproj .gguf)",
    "asr_server_binary": "llama-server çalıştırılabiliri; boşsa PATH'te aranır",
    "asr_context": "terimleri cümle içinde anlatan paragraf; çıplak liste işe yaramaz",
    "asr_timeout": "bir deşifre isteğinin azami süresi (saniye)",
    "dictate_microphone": "dikte mikrofonu, ffmpeg biçim:aygıt yazımıyla; boşsa sistem varsayılanı",
    "dictate_max_seconds": "bir diktenin azami kayıt süresi (saniye)",
    "dictate_start_sound": "kayıt başlarken çalınan ses; boşsa üretilen ton",
    "dictate_stop_sound": "kayıt bitince çalınan ses; boşsa üretilen ton",
    "dictate_done_sound": "metin panoya konunca çalınan ses; boşsa üretilen ton",
    "dictate_error_sound": "dikte başarısız olunca çalınan ses; boşsa üretilen ton",
}
"""Üretilen config dosyasındaki açıklama satırları.

Varsayılan değerlerin kendisi `Config`'ten okunur; burada yalnızca ne işe
yaradıkları yazar. Böylece varsayılan değişince dosya kendiliğinden güncel kalır.
"""

_POLICY_NOTES: dict[SegmentType, str] = {
    SegmentType.CODE_BLOCK: "kod blokları — okunmaz, kısaca anons edilir",
    SegmentType.TABLE: "Markdown tabloları",
    SegmentType.URL: "çıplak bağlantı adresleri",
    SegmentType.FILE_PATH: "dosya yolları — 'read' yalnızca dosya adını okur",
    SegmentType.HORIZONTAL_RULE: "yatay çizgiler",
    SegmentType.INLINE_CODE: "satır içi `kod` parçaları",
    SegmentType.PROSE: "düz metin",
    SegmentType.HEADING: "başlıklar",
    SegmentType.LIST_ITEM: "liste maddeleri",
    SegmentType.QUOTE: "alıntı blokları",
}


def render_default_config() -> str:
    """Varsayılan ayarları, açıklamalı bir TOML metni olarak üretir.

    Değerler `Config` ve `DEFAULT_POLICY`'den okunduğu için ikinci bir doğruluk
    kaynağı oluşmaz; varsayılan değişirse üretilen dosya da değişir.
    """
    defaults = Config()
    lines = [
        _("# Pakize yapılandırması"),
        _("# 'pakize config --init' ile üretildi."),
        _("# Bu dosyayı silersen Pakize varsayılanlarla çalışmaya devam eder."),
        "",
    ]

    for field, description in _FIELD_NOTES.items():
        value = getattr(defaults, field)
        line = f"{field} = {_toml_value(value)}"
        # TOML'da boş değer yok; tanımsız ayarları örnek olarak yorumda bırakırız.
        if value is None:
            line = f"# {field} = {_toml_value(_EXAMPLE_VALUES[field])}"
        lines.append(_with_comment(line, _(description)))

    lines += [
        "",
        "[policy]",
        _(
            '# Her segment tipi için: "read" (oku), "announce" (anons et), '
            '"skip" (atla)'
        ),
    ]
    for segment_type, description in _POLICY_NOTES.items():
        action = DEFAULT_POLICY[segment_type]
        line = f'{segment_type.value} = "{action.value}"'
        lines.append(_with_comment(line, _(description)))

    lines += [
        "",
        "[asr_replacements]",
        _("# Deşifre çıktısında düzeltilecek yazımlar: \"yanlış\" = \"doğru\""),
        _("# Yalnız bütün kelime eşleşir; büyük-küçük harf ayrı sayılır."),
        '# "Yuvı" = "uv"',
    ]

    return "\n".join(lines) + "\n"


_COMMENT_COLUMN = 44


def _with_comment(line: str, description: str) -> str:
    """Ayar satırının sağına, hizalı bir açıklama yorumu ekler.

    Satır hizalama sütununu aşarsa yorum yine de tek boşlukla ayrılır; aksi
    hâlde uzun değerlerde açıklama satıra yapışırdı.
    """
    padding = max(_COMMENT_COLUMN - len(line), 1)
    return f"{line}{' ' * padding}# {description}"


_EXAMPLE_VALUES: dict[str, object] = {
    "translate_to": "tr",
    "piper_model": "~/.local/share/piper/tr_TR-dfki-medium.onnx",
    "piper_binary": "~/.local/bin/piper",
    "asr_server_url": "http://127.0.0.1:8099",
    "asr_model": "~/.local/share/pakize/asr/Qwen3-ASR-1.7B-Q8_0.gguf",
    "asr_mmproj": "~/.local/share/pakize/asr/mmproj-Qwen3-ASR-1.7B-Q8_0.gguf",
    "asr_server_binary": "~/.local/bin/llama-server",
    "asr_context": "Pakize'yi uv ile kuruyorum; seslendirmede edge-tts ve Piper var.",
    "dictate_microphone": "pulse:default",
    "dictate_start_sound": "~/Music/sounds/start.mp3",
    "dictate_stop_sound": "~/Music/sounds/stop.mp3",
    "dictate_done_sound": "~/Music/sounds/done.mp3",
    "dictate_error_sound": "~/Music/sounds/error.mp3",
}
"""Varsayılanı tanımsız olan ayarlar için yorumda gösterilecek örnek değerler."""


def write_default_config(path: Path | None = None) -> Path:
    """Varsayılan config dosyasını yazar.

    Var olan dosyanın üzerine yazmaz; ayarlarını kaybetmemen için
    `FileExistsError` fırlatır.
    """
    target = path or config_path()
    if target.exists():
        raise FileExistsError(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_default_config(), encoding="utf-8")
    return target


def set_config_value(key: str, raw_value: str, path: Path | None = None) -> str:
    """Tek bir ayarı config dosyasına yazar; yazılan TOML değerini döner.

    Dosya yoksa açıklamalı varsayılan içerikle oluşturulur; varsa yalnızca
    ilgili satır değiştirilir, kullanıcının diğer satırları olduğu gibi kalır.
    """
    value = _parse_setting(key, raw_value)
    rendered = _toml_value(value)
    line = f"{key} = {rendered}"
    if key in _FIELD_NOTES:
        line = _with_comment(line, _(_FIELD_NOTES[key]))

    target = path or config_path()
    if target.is_file():
        content = target.read_text(encoding="utf-8")
    else:
        content = render_default_config()

    lines = _set_line(content.splitlines(), key, line)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rendered


REPLACEMENTS_TABLE = "asr_replacements"


def set_replacement(wrong: str, right: str, path: Path | None = None) -> str | None:
    """Düzeltme tablosuna bir satır yazar; anahtar varsa eski değerini döner.

    Dosya yoksa açıklamalı varsayılanlarla oluşturulur; tablo yoksa dosyanın
    sonuna açılır. Diğer satırlara dokunulmaz. Anahtar her zaman tırnaklı
    yazılır: Türkçe harfler TOML'un çıplak anahtarında geçerli değil.
    """
    if not wrong.strip() or not right.strip():
        raise ValueError(_("Yanlış ve doğru yazım boş olamaz."))

    target = path or config_path()
    lines = _read_config_lines(target)
    start, end = _table_span(lines, REPLACEMENTS_TABLE)
    if start is None:
        lines += ["", f"[{REPLACEMENTS_TABLE}]"]
        start, end = len(lines), len(lines)

    new_line = f"{_toml_value(wrong)} = {_toml_value(right)}"
    for index in range(start, end):
        entry = _table_entry(lines[index])
        if entry is not None and entry[0] == wrong:
            lines[index] = new_line
            _write_config_lines(target, lines)
            return entry[1]

    # Tablonun sonuna, sondaki boş satırların üstüne eklenir.
    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, new_line)
    _write_config_lines(target, lines)
    return None


def remove_replacement(wrong: str, path: Path | None = None) -> bool:
    """Düzeltme tablosundan bir satırı siler; satır yoksa False döner."""
    target = path or config_path()
    if not target.is_file():
        return False
    lines = target.read_text(encoding="utf-8").splitlines()
    start, end = _table_span(lines, REPLACEMENTS_TABLE)
    if start is None:
        return False
    for index in range(start, end):
        entry = _table_entry(lines[index])
        if entry is not None and entry[0] == wrong:
            del lines[index]
            _write_config_lines(target, lines)
            return True
    return False


def _read_config_lines(target: Path) -> list[str]:
    if target.is_file():
        return target.read_text(encoding="utf-8").splitlines()
    return render_default_config().splitlines()


def _write_config_lines(target: Path, lines: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _table_span(lines: list[str], table: str) -> tuple[int | None, int]:
    """Bir tablonun gövdesinin satır aralığı: (başlıktan sonraki ilk satır, bitiş).

    Tablo yoksa (None, len). Gövde bir sonraki `[başlık]` satırına kadar sürer.
    """
    header = f"[{table}]"
    for index, line in enumerate(lines):
        if line.strip() == header:
            end = next(
                (
                    later
                    for later in range(index + 1, len(lines))
                    if lines[later].lstrip().startswith("[")
                ),
                len(lines),
            )
            return index + 1, end
    return None, len(lines)


_TABLE_ENTRY = re.compile(r'^\s*(?:"((?:[^"\\]|\\.)*)"|([A-Za-z0-9_-]+))\s*=\s*(.*)$')


def _table_entry(line: str) -> tuple[str, str] | None:
    """Tablo satırını (anahtar, ham değer) olarak okur; satır ayar değilse None.

    Anahtar tırnaklı ya da çıplak olabilir; yorum satırları ayar sayılmaz.
    """
    match = _TABLE_ENTRY.match(line)
    if match is None:
        return None
    quoted, bare, raw_value = match.groups()
    key = _unescape(quoted) if quoted is not None else bare
    value = raw_value.split("#", 1)[0].strip() if not raw_value.startswith('"') else raw_value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = _unescape(value[1:-1])
    return key, value


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _parse_setting(key: str, raw: str) -> object:
    """CLI'dan gelen metin değeri ayarın tipine çevirir; tanımazsa hata verir."""
    if key in _PATH_FIELDS:
        return raw

    caster = _SCALAR_FIELDS.get(key)
    if caster is None:
        valid_keys = ", ".join([*_SCALAR_FIELDS, *_PATH_FIELDS])
        raise ValueError(
            _("Bilinmeyen ayar: {key!r} (geçerli: {valid_keys})").format(
                key=key, valid_keys=valid_keys
            )
        )

    if caster is bool:
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        raise ValueError(
            _("{key} için true/false bekleniyor: {value!r}").format(
                key=key, value=raw
            )
        )

    try:
        return caster(raw)
    except ValueError as exc:
        raise ValueError(
            _("{key} için geçersiz değer: {value!r} ({type} bekleniyor)").format(
                key=key, value=raw, type=caster.__name__
            )
        ) from exc


def _set_line(lines: list[str], key: str, new_line: str) -> list[str]:
    """Üst düzey bölümde ayarın satırını değiştirir ya da uygun yere ekler.

    Yalnızca ilk tablo başlığına (`[policy]` gibi) kadar bakılır; aksi hâlde
    tablo içindeki aynı adlı bir anahtar yanlışlıkla değişirdi. Yorumlanmış
    (`# translate_to = ...`) satır da eşleşir — ayar böylece etkinleşir.
    """
    pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
    header = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )

    for i in range(header):
        if pattern.match(lines[i]):
            return [*lines[:i], new_line, *lines[i + 1 :]]

    # Anahtar yoksa üst düzey bölümün sonuna, başlıktan önceki boş
    # satırların üstüne eklenir; böylece başlık öncesi boşluk korunur.
    insert_at = header
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    return [*lines[:insert_at], new_line, *lines[insert_at:]]


def _toml_value(value: object) -> str:
    """Python değerini TOML gösterimine çevirir.

    Ters bölü TOML dizgisinde kaçış başlatır: `%TEMP%\\pakize` gibi bir Windows
    yolunu olduğu gibi yazmak, kendi ürettiğimiz dosyayı okunamaz kılardı.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _merge_policy(
    base: dict[SegmentType, Action], table: dict
) -> dict[SegmentType, Action]:
    """Config'teki `[policy]` tablosunu varsayılan politikayla birleştirir.

    Tanınmayan segment tipi veya eylem adı sessizce yutulmaz; erken hata
    vermek, kullanıcının yazım hatasını fark etmesini sağlar.
    """
    merged = dict(base)
    for raw_type, raw_action in table.items():
        try:
            segment_type = SegmentType(raw_type)
        except ValueError as exc:
            raise ValueError(
                _("Bilinmeyen segment tipi: {type!r}").format(type=raw_type)
            ) from exc
        try:
            merged[segment_type] = Action(raw_action)
        except ValueError as exc:
            raise ValueError(
                _(
                    "{type} için bilinmeyen eylem: {action!r} "
                    "(geçerli: read, announce, skip)"
                ).format(type=raw_type, action=raw_action)
            ) from exc
    return merged


def _read_replacements(table: dict) -> dict[str, str]:
    """Config'teki `[asr_replacements]` tablosunu okur.

    Dizge olmayan değer sessizce `str`'e çevrilmez: `uv = 1` gibi bir yazım
    hatası metne "1" basardı. Boş anahtar da reddedilir; hiçbir şeyle eşleşmez,
    kullanıcı neden çalışmadığını anlayamazdı.
    """
    replacements: dict[str, str] = {}
    for wrong, right in table.items():
        if not wrong.strip():
            raise ValueError(_("[asr_replacements] içinde boş anahtar var."))
        if not isinstance(right, str):
            raise ValueError(
                _("[asr_replacements] içinde {key!r} için metin bekleniyor.").format(
                    key=wrong
                )
            )
        replacements[wrong] = right
    return replacements
