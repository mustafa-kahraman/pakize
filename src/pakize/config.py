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

    fallback_engine: str | None = None
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

    for key in ("piper_model", "output_dir"):
        if data.get(key):
            overrides[key] = Path(str(data[key])).expanduser()

    policy_table = data.get("policy")
    if isinstance(policy_table, dict):
        overrides["policy"] = _merge_policy(base.policy, policy_table)

    return replace(base, **overrides)


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
