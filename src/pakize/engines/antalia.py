"""antalia-mini ile tamamen çevrimdışı Türkçe seslendirme.

antalia-mini (https://huggingface.co/cloud0day3/antalia-mini) 7,6 milyon
parametrelik, tek sesli, CPU'da çalışan bir Türkçe TTS modelidir (Apache-2.0).
Çıkışı 48 kHz mono. EMA'nın yanında ikinci isteğe bağlı çevrimdışı motordur;
varsayılanlar değişmez (edge birincil, piper yedek).

Model torch ister; EMA gibi kullanıcının ayrıca kurduğu bir Python ortamında,
`antalia_python` ile gösterilen yorumlayıcıyla `antalia_worker.py` alt süreç
olarak çalışır. İşçi sürecin yönetimi `worker.py`'de ortaktır; burada yalnız
antalia'ya özgü olan durur: kurulum komutları ve isteğin alanları.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ..config import Config
from ..i18n import _
from . import antalia_worker
from .base import EngineError, EngineUnavailable
from .worker import WorkerEngine, python_example

WORKER_PATH = Path(antalia_worker.__file__)
"""Alt süreçte çalışan betik; testler protokolü taklit eden bir sahteyle değiştirir."""

ENV_DIR_EXAMPLE = "~/.local/share/pakize-antalia"

WHEEL_URL = (
    "https://huggingface.co/cloud0day3/antalia-mini/resolve/"
    f"{antalia_worker.REVISION}/antalia_mini-1.0.0-py3-none-any.whl"
)
"""Paket PyPI'da değil; sabit revizyondaki wheel doğrudan Hugging Face'ten kurulur."""

VENV_COMMAND = "uv venv --python 3.12 {env}"
"""antalia ortamını açan komut; `{env}` ortam dizini."""

TORCH_COMMAND = (
    "uv pip install --python {python} torch --index https://download.pytorch.org/whl/cpu"
)
"""torch'un CPU sürümünü kuran komut; `--index` tek dizin (bkz. `ema.py`)."""

INSTALL_COMMAND = f'uv pip install --python {{python}} "antalia-mini @ {WHEEL_URL}"'
"""antalia-mini'yi sabit wheel'den kuran komut; `{python}` ortamın yolu ya da yorumlayıcısı."""


def install_steps(python: str) -> str:
    """Kurulum mesajlarındaki üç komut, satır başına ikişer boşlukla."""
    return "\n".join(
        f"  {command.format(env=python, python=python)}"
        for command in (VENV_COMMAND, TORCH_COMMAND, INSTALL_COMMAND)
    )


class AntaliaEngine(WorkerEngine):
    name: ClassVar[str] = "antalia"
    label: ClassVar[str] = "antalia"
    config_key: ClassVar[str] = "antalia_python"

    def __init__(self, config: Config, worker_path: Path | None = None) -> None:
        super().__init__(config, worker_path or WORKER_PATH)

    def _python(self) -> Path:
        python = self.config.antalia_python
        if python is None:
            raise EngineUnavailable(
                _(
                    "antalia motoru için ayrı bir Python ortamı gerekli. Kurmak için:\n"
                    "{steps}\n"
                    "sonra yorumlayıcının yolunu config'e yaz:\n"
                    '  antalia_python = "{example}"'
                ).format(
                    steps=install_steps(ENV_DIR_EXAMPLE),
                    example=python_example(ENV_DIR_EXAMPLE),
                )
            )
        return python

    async def synthesize(self, text: str, destination: Path) -> None:
        # Kesme işaretleri olduğu gibi gider: antalia onları kendisi çözüyor.
        rate = self.config.rate
        if rate <= 0:
            raise EngineError(_("rate pozitif olmalı"))
        request = {
            "text": text,
            "out": str(destination),
            "rate": rate,
            "volume": self.config.volume,
        }
        await self._run(request, text, destination)

    def _setup_message(self, message: dict[str, Any], python: Path) -> str:
        code = message.get("code")
        if code == "missing_package":
            # Gösterilen yorumlayıcı sistem Python'u olabilir; torch'u oraya değil
            # ayrı bir ortama kurmayı öneririz.
            return _(
                "antalia ortamında ({python}) gerekli paketler yok: {error}\n"
                "Ayrı bir ortam açıp paketleri oraya kur:\n"
                "{steps}\n"
                "sonra yorumlayıcının yolunu config'e yaz:\n"
                '  antalia_python = "{example}"'
            ).format(
                python=python,
                error=message.get("error", ""),
                steps=install_steps(ENV_DIR_EXAMPLE),
                example=python_example(ENV_DIR_EXAMPLE),
            )
        if code == "wrong_version":
            return _(
                "antalia-mini {installed} kurulu; tam olarak {required} gerekli. "
                "Kurmak için:\n  {install}"
            ).format(
                installed=message.get("installed", "?"),
                required=antalia_worker.REQUIRED_VERSION,
                install=INSTALL_COMMAND.format(python=python),
            )
        return super()._setup_message(message, python)
