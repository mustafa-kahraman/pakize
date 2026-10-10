"""EMA Lightning ile tamamen çevrimdışı Türkçe seslendirme.

EMA Lightning (https://huggingface.co/canberkkkkkk/ema-lightning) yerelde,
CPU'da çalışan tek sesli bir Türkçe TTS modelidir. Piper gibi ağ istemez;
Türkçe doğallığı Piper'ın üstündedir.

Model torch ister ve Pakize'nin çekirdeği ağır makine öğrenmesi bağımlılıkları
taşımaz (bkz. `piper.py`, `asr/qwen.py`). Bu yüzden EMA, kullanıcının ayrıca
kurduğu bir Python ortamında çalışır: `ema_python` o ortamın yorumlayıcısını
gösterir, Pakize `ema_worker.py` betiğini onunla alt süreç olarak başlatır.
İşçi sürecin yönetimi (`worker.py`) antalia motoruyla ortaktır; burada yalnız
EMA'ya özgü olan durur: kurulum komutları, hız aralığı, kesme temizliği.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ..config import Config
from ..i18n import _
from . import ema_worker
from .base import EngineError, EngineUnavailable
from .worker import WorkerEngine, python_example

WORKER_PATH = Path(ema_worker.__file__)
"""Alt süreçte çalışan betik; testler protokolü taklit eden bir sahteyle değiştirir."""

ENV_DIR_EXAMPLE = "~/.local/share/pakize-ema"

VENV_COMMAND = "uv venv --python 3.12 {env}"
"""EMA ortamını açan komut; `{env}` ortam dizini.

Python sürümü bilerek sabit: ema-lightning 1.0.1 Python ≥ 3.11 ister; uv
klasördeki `.python-version`'a ya da sistemin 3.10'una düşerse kurulum
"does not satisfy Python>=3.11" ile kalıyordu.
"""

INSTALL_COMMAND = (
    "uv pip install --python {python} ema-lightning==1.0.1 torch "
    "--index https://download.pytorch.org/whl/cpu"
)
"""EMA ortamına paketleri kuran komut; `{python}` ortamın yolu ya da yorumlayıcısı.

`--index` (tek dizin) bilerek: `--index-url` + `--extra-index-url` ikilisinde
uv PyPI'yı öne alır ve torch'un birkaç GB'lık CUDA sürümünü kurar. PyTorch'un
CPU dizini ema-lightning'in diğer bağımlılıklarını da barındırmadığından uv
eksikleri PyPI'dan tamamlar; ölçülen kurulum yaklaşık 400 MB.
"""


class EmaEngine(WorkerEngine):
    name: ClassVar[str] = "ema"
    label: ClassVar[str] = "EMA"
    config_key: ClassVar[str] = "ema_python"

    def __init__(self, config: Config, worker_path: Path | None = None) -> None:
        super().__init__(config, worker_path or WORKER_PATH)

    def _python(self) -> Path:
        python = self.config.ema_python
        if python is None:
            raise EngineUnavailable(
                _(
                    "ema motoru için ayrı bir Python ortamı gerekli. Kurmak için:\n"
                    "  {venv}\n"
                    "  {install}\n"
                    "sonra yorumlayıcının yolunu config'e yaz:\n"
                    '  ema_python = "{example}"'
                ).format(
                    venv=VENV_COMMAND.format(env=ENV_DIR_EXAMPLE),
                    install=INSTALL_COMMAND.format(python=ENV_DIR_EXAMPLE),
                    example=python_example(ENV_DIR_EXAMPLE),
                )
            )
        return python

    async def synthesize(self, text: str, destination: Path) -> None:
        request = {
            "text": ema_worker.prepare_text(text),
            "out": str(destination),
            "speed": self._speed(),
            "volume": self.config.volume,
        }
        await self._run(request, text, destination)

    def _speed(self) -> float:
        """`rate` çarpanını EMA hızına çevirir; aralık dışı değer açık hata verir."""
        rate = self.config.rate
        try:
            return ema_worker.speed_from_rate(rate)
        except ValueError:
            raise EngineError(
                _("rate {rate} EMA için geçersiz; {low} ile {high} arasında olmalı").format(
                    rate=rate, low=ema_worker.SPEED_MIN, high=ema_worker.SPEED_MAX
                )
            ) from None

    def _setup_message(self, message: dict[str, Any], python: Path) -> str:
        code = message.get("code")
        if code == "missing_package":
            # Gösterilen yorumlayıcı sistem Python'u olabilir; torch'u oraya değil
            # ayrı bir ortama kurmayı öneririz.
            return _(
                "EMA ortamında ({python}) gerekli paketler yok: {error}\n"
                "Ayrı bir ortam açıp paketleri oraya kur:\n"
                "  {venv}\n"
                "  {install}\n"
                "sonra yorumlayıcının yolunu config'e yaz:\n"
                '  ema_python = "{example}"'
            ).format(
                python=python,
                error=message.get("error", ""),
                venv=VENV_COMMAND.format(env=ENV_DIR_EXAMPLE),
                install=INSTALL_COMMAND.format(python=ENV_DIR_EXAMPLE),
                example=python_example(ENV_DIR_EXAMPLE),
            )
        if code == "wrong_version":
            return _(
                "ema-lightning {installed} kurulu; güvenli yükleme için tam olarak "
                "{required} gerekli. Kurmak için:\n  {install}"
            ).format(
                installed=message.get("installed", "?"),
                required=ema_worker.REQUIRED_VERSION,
                install=INSTALL_COMMAND.format(python=python),
            )
        return super()._setup_message(message, python)
