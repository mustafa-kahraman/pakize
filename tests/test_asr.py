"""Konuşmayı metne çeviren motorun testleri.

Hermetiktir: ağa çıkılmaz, sunucu çağrısı yamalanır.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pakize.asr import AsrError, AsrUnavailable, create_asr_engine
from pakize.asr import http as http_module
from pakize.asr import qwen as qwen_module
from pakize.asr.qwen import QwenEngine
from pakize.asr.replacements import apply_replacements
from pakize.config import Config


@pytest.fixture
def audio_file(tmp_path) -> Path:
    path = tmp_path / "kayit.wav"
    path.write_bytes(b"RIFF sahte wav")
    return path


@pytest.fixture
def config() -> Config:
    return replace(Config(), asr_server_url="http://127.0.0.1:8099")


@pytest.fixture
def server(monkeypatch):
    """`post_json`'ı yamalar; gönderilen gövdeyi kaydeder, yanıtı ayarlanır."""
    sent: dict = {}
    settings = {"text": "language Turkish<asr_text>Merhaba dünya.", "response": None}

    def fake_post(url, payload, timeout):
        sent["url"] = url
        sent["payload"] = payload
        sent["timeout"] = timeout
        if settings["response"] is not None:
            return settings["response"]
        return {"choices": [{"message": {"content": settings["text"]}}]}

    monkeypatch.setattr(qwen_module, "post_json", fake_post)
    return type("Server", (), {"sent": sent, "settings": settings})


def test_sunucu_adresi_yoksa_kullanilamaz():
    engine = QwenEngine(Config())

    with pytest.raises(AsrUnavailable, match="sunucu adresi gerekli"):
        engine.ensure_available()


def test_hazir_yapilandirma_gecerlidir(config):
    QwenEngine(config).ensure_available()


def test_dil_oneki_ayiklanir(config, server, audio_file):
    assert QwenEngine(config).transcribe(audio_file) == "Merhaba dünya."


def test_onek_yoksa_icerik_oldugu_gibi_doner(config, server, audio_file):
    server.settings["text"] = "  Önektsiz metin.  "

    assert QwenEngine(config).transcribe(audio_file) == "Önektsiz metin."


def test_baglam_sistem_mesajina_konur(server, audio_file):
    context = "Pakize'yi uv ile kuruyorum; seslendirmede Piper var."
    engine = QwenEngine(
        replace(
            Config(), asr_server_url="http://127.0.0.1:8099", asr_context=context
        )
    )

    engine.transcribe(audio_file)

    messages = server.sent["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == context


def test_baglam_yoksa_sistem_mesaji_yok(config, server, audio_file):
    QwenEngine(config).transcribe(audio_file)

    roles = [message["role"] for message in server.sent["payload"]["messages"]]
    assert "system" not in roles


def test_yalniz_bosluktan_olusan_baglam_gonderilmez(server, audio_file):
    engine = QwenEngine(
        replace(Config(), asr_server_url="http://127.0.0.1:8099", asr_context="  \n")
    )

    engine.transcribe(audio_file)

    roles = [message["role"] for message in server.sent["payload"]["messages"]]
    assert "system" not in roles


def test_duzeltme_tablosu_desifre_ciktisina_uygulanir(server, audio_file):
    server.settings["text"] = "language Turkish<asr_text>Yuvı ile kurdum."
    engine = QwenEngine(
        replace(
            Config(),
            asr_server_url="http://127.0.0.1:8099",
            asr_replacements={"Yuvı": "uv"},
        )
    )

    assert engine.transcribe(audio_file) == "uv ile kurdum."


def test_ses_base64_olarak_gonderilir(config, server, audio_file):
    import base64

    QwenEngine(config).transcribe(audio_file)

    audio = server.sent["payload"]["messages"][-1]["content"][0]["input_audio"]
    assert base64.b64decode(audio["data"]) == audio_file.read_bytes()
    assert audio["format"] == "wav"


def test_adresin_sonundaki_egik_cizgi_yinelenmez(server, audio_file):
    engine = QwenEngine(
        replace(Config(), asr_server_url="http://127.0.0.1:8099/")
    )

    engine.transcribe(audio_file)

    assert server.sent["url"] == "http://127.0.0.1:8099/v1/chat/completions"


def test_tanimayan_ses_bicimi_hata_verir(config, server, tmp_path):
    other = tmp_path / "kayit.ogg"
    other.write_bytes(b"ogg")

    with pytest.raises(AsrError, match="Tanınmayan ses biçimi"):
        QwenEngine(config).transcribe(other)


def test_bos_yanit_anlasilir_hata_verir(config, server, audio_file):
    server.settings["response"] = {"choices": []}

    with pytest.raises(AsrError, match="beklenmedik bir yanıt"):
        QwenEngine(config).transcribe(audio_file)


def test_metin_yerine_other_tip_gelirse_hata_verir(config, server, audio_file):
    server.settings["response"] = {"choices": [{"message": {"content": None}}]}

    with pytest.raises(AsrError, match="beklenmedik bir yanıt"):
        QwenEngine(config).transcribe(audio_file)


def test_bilinmeyen_motor_hata_verir(config):
    with pytest.raises(AsrError, match="Bilinmeyen deşifre motoru"):
        create_asr_engine("whisper", config)


def test_config_motoru_uretilir(config):
    assert isinstance(create_asr_engine(config.asr_engine, config), QwenEngine)


def test_zaman_asimi_okunabilir_hataya_cevrilir(monkeypatch):
    def fake_urlopen(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(AsrError, match="yanıt vermedi"):
        http_module.post_json("http://127.0.0.1:8099/x", {}, timeout=1.0)


def test_gecersiz_json_hataya_cevrilir(monkeypatch):
    class FakeResponse:
        def read(self):
            return "düz metin".encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        http_module.urllib.request, "urlopen", lambda request, timeout: FakeResponse()
    )

    with pytest.raises(AsrError, match="geçerli JSON"):
        http_module.post_json("http://127.0.0.1:8099/x", {}, timeout=1.0)


def test_gonderilen_govde_json_olarak_kodlanir(monkeypatch):
    sent: dict = {}

    class FakeResponse:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        sent["data"] = request.data
        sent["headers"] = request.headers
        return FakeResponse()

    monkeypatch.setattr(http_module.urllib.request, "urlopen", fake_urlopen)

    http_module.post_json("http://127.0.0.1:8099/x", {"a": 1}, timeout=1.0)

    assert json.loads(sent["data"]) == {"a": 1}
    assert sent["headers"]["Content-type"] == "application/json"


def test_duzeltme_yalniz_butun_kelimeye_uygulanir():
    table = {"Apab": "EPUB"}

    assert apply_replacements("Apab dosyası", table) == "EPUB dosyası"
    assert apply_replacements("Apabey geldi", table) == "Apabey geldi"


def test_duzeltme_noktalama_yaninda_da_calisir():
    assert apply_replacements("(Yuvı), Yuvı.", {"Yuvı": "uv"}) == "(uv), uv."


def test_duzeltme_harf_buyuklugune_duyarlidir():
    assert apply_replacements("yuvı", {"Yuvı": "uv"}) == "yuvı"


def test_ortusen_anahtarlarda_uzun_olan_kazanir():
    table = {"TTS": "tts", "Ecdi TTS": "edge-tts"}

    assert apply_replacements("Ecdi TTS ve TTS", table) == "edge-tts ve tts"


def test_duzeltmeler_zincirlenmez():
    table = {"a": "b", "b": "c"}

    assert apply_replacements("a b", table) == "b c"


def test_ozel_karakterli_anahtar_duz_metin_sayilir():
    assert apply_replacements("C++ ve Cxx", {"C++": "Cpp"}) == "Cpp ve Cxx"


def test_bos_tablo_metne_dokunmaz():
    assert apply_replacements("Merhaba.", {}) == "Merhaba."


# --- bağlam kopyalaması ------------------------------------------------------

_CONTEXT = "Pakize, benim yazdığım programın adı. Seslendirmede edge-tts var."


@pytest.fixture
def echoing_server(monkeypatch):
    """İlk istekte bağlamı kopyalayan, ikincisinde sesi yazan sahte sunucu."""
    payloads: list[dict] = []

    def fake_post(url, payload, timeout):
        payloads.append(payload)
        has_context = payload["messages"][0]["role"] == "system"
        content = _CONTEXT if has_context else "Merhaba Pakize."
        return {"choices": [{"message": {"content": f"<asr_text>{content}"}}]}

    monkeypatch.setattr(qwen_module, "post_json", fake_post)
    return payloads


def test_baglam_kopyalanirsa_baglamsiz_yeniden_sorulur(echoing_server, audio_file):
    config = replace(
        Config(), asr_server_url="http://127.0.0.1:8099", asr_context=_CONTEXT
    )

    text = QwenEngine(config).transcribe(audio_file)

    assert text == "Merhaba Pakize."
    assert len(echoing_server) == 2
    assert echoing_server[1]["messages"][0]["role"] == "user"


def test_baglamin_bir_cumlesi_kopyalansa_da_yakalanir(server, audio_file):
    config = replace(
        Config(), asr_server_url="http://127.0.0.1:8099", asr_context=_CONTEXT
    )
    server.settings["text"] = "<asr_text>Seslendirmede edge-tts var."
    calls = {"count": 0}
    original = qwen_module.post_json

    def counting(url, payload, timeout):
        calls["count"] += 1
        return original(url, payload, timeout)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(qwen_module, "post_json", counting)
        QwenEngine(config).transcribe(audio_file)

    assert calls["count"] == 2


def test_baglamdaki_terim_ciktida_gecince_kopyalama_sayilmaz(server, audio_file):
    """Terimin kendisi ("Pakize") tam da bağlamın işi; ikinci istek atılmaz."""
    config = replace(
        Config(), asr_server_url="http://127.0.0.1:8099", asr_context=_CONTEXT
    )
    server.settings["text"] = "<asr_text>Merhaba Pakize, nasılsın?"

    text = QwenEngine(config).transcribe(audio_file)

    assert text == "Merhaba Pakize, nasılsın?"
    assert server.sent["payload"]["messages"][0]["role"] == "system"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_CONTEXT, True),
        ("Pakize, benim yazdığım programın adı", True),
        ("Merhaba Pakize.", False),
        ("", False),
    ],
)
def test_kopyalama_tespiti(text, expected):
    assert qwen_module._echoes_context(text, _CONTEXT) is expected
