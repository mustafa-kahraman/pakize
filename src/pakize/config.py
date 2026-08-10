"""Pakize yapılandırması.

Ayarlar üç katmandan gelir; sonraki öncekini ezer:
1. Buradaki varsayılanlar
2. `~/.config/pakize/config.toml`
3. CLI bayrakları

Segment politikası da config'te yaşar; böylece "kodu atla" davranışı koda
gömülü bir kural değil, kullanıcının değiştirebildiği bir tercih olur.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from .models import Action, SegmentType

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

DEFAULT_OUTPUT_DIR = Path("/tmp/pakize")
"""Çıktı yolu verilmediğinde seslerin yazıldığı dizin."""


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

    stream: bool = True
    """Parçalar hazır oldukça sırayla çal; hepsinin bitmesini bekleme."""

    policy: dict[SegmentType, Action] = field(
        default_factory=lambda: dict(DEFAULT_POLICY)
    )

    piper_model: Path | None = None
    """Piper ses modelinin (.onnx) yolu; None ise Piper motoru kullanılamaz."""

    piper_binary: Path | None = None
    """Piper çalıştırılabilirinin yolu; None ise PATH üzerinden aranır."""

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
    """Kullanıcı config dosyasının yolu (XDG_CONFIG_HOME'a saygı duyar)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "pakize" / "config.toml"


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


def _apply_overrides(base: Config, data: dict) -> Config:
    """TOML sözlüğündeki tanınan anahtarları Config üzerine uygular."""
    scalar_fields = {
        "voice": str,
        "engine": str,
        "fallback_engine": str,
        "rate": float,
        "pitch_hz": int,
        "volume": float,
        "max_chunk_chars": int,
        "normalize_decimals": bool,
        "stream": bool,
    }

    overrides: dict = {}
    for key, caster in scalar_fields.items():
        if key in data and data[key] is not None:
            overrides[key] = caster(data[key])

    for key in ("piper_model", "piper_binary", "output_dir"):
        if data.get(key):
            overrides[key] = Path(str(data[key])).expanduser()

    policy_table = data.get("policy")
    if isinstance(policy_table, dict):
        overrides["policy"] = _merge_policy(base.policy, policy_table)

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
    "piper_model": "Piper ses modelinin (.onnx) yolu",
    "piper_binary": "piper çalıştırılabiliri; boşsa PATH'te aranır",
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
    satirlar = [
        "# Pakize yapılandırması",
        "# 'pakize config --init' ile üretildi.",
        "# Bu dosyayı silersen Pakize varsayılanlarla çalışmaya devam eder.",
        "",
    ]

    for alan, aciklama in _FIELD_NOTES.items():
        deger = getattr(defaults, alan)
        satir = f"{alan} = {_toml_value(deger)}"
        # TOML'da boş değer yok; tanımsız ayarları örnek olarak yorumda bırakırız.
        if deger is None:
            satir = f"# {alan} = {_toml_value(_ORNEK_DEGERLER[alan])}"
        satirlar.append(_yorumla(satir, aciklama))

    satirlar += [
        "",
        "[policy]",
        '# Her segment tipi için: "read" (oku), "announce" (anons et), "skip" (atla)',
    ]
    for segment_type, aciklama in _POLICY_NOTES.items():
        action = DEFAULT_POLICY[segment_type]
        satir = f'{segment_type.value} = "{action.value}"'
        satirlar.append(_yorumla(satir, aciklama))

    return "\n".join(satirlar) + "\n"


_YORUM_SUTUNU = 44


def _yorumla(satir: str, aciklama: str) -> str:
    """Ayar satırının sağına, hizalı bir açıklama yorumu ekler.

    Satır hizalama sütununu aşarsa yorum yine de tek boşlukla ayrılır; aksi
    hâlde uzun değerlerde açıklama satıra yapışırdı.
    """
    bosluk = max(_YORUM_SUTUNU - len(satir), 1)
    return f"{satir}{' ' * bosluk}# {aciklama}"


_ORNEK_DEGERLER: dict[str, object] = {
    "piper_model": "~/.local/share/piper/tr_TR-dfki-medium.onnx",
    "piper_binary": "~/.local/bin/piper",
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


def _toml_value(value: object) -> str:
    """Python değerini TOML gösterimine çevirir."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


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
            raise ValueError(f"Bilinmeyen segment tipi: {raw_type!r}") from exc
        try:
            merged[segment_type] = Action(raw_action)
        except ValueError as exc:
            raise ValueError(
                f"{raw_type} için bilinmeyen eylem: {raw_action!r} "
                f"(geçerli: read, announce, skip)"
            ) from exc
    return merged
