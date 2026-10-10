"""Pakize arayüz dili.

Kaynak metinler Türkçedir; katalog yalnızca Türkçe → İngilizce eşlemesi tutar
(gettext geleneği). Eşlemesi olmayan metin Türkçe görünür — eksik çeviri,
programı asla kırmaz.

Dil şu sırayla çözülür:
1. `set_language()` ile zorlanan dil (testler ve gelecekteki bayraklar)
2. Config dosyasındaki `ui_language`
3. Ortam değişkenleri: `LC_ALL` > `LC_MESSAGES` > `LANG`

Türkçe olmayan her ortam İngilizce görür; İngilizce güvenli ortak paydadır.
"""

from __future__ import annotations

import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SUPPORTED = ("tr", "en")

_forced: str | None = None
_resolved: str | None = None


def set_language(lang: str | None) -> None:
    """Dili elle sabitler; None verilirse yeniden tespit edilir."""
    global _forced, _resolved
    _forced = lang
    _resolved = None


def language() -> str:
    """Etkin arayüz dilini döner; ilk çağrıda tespit edip önbelleğe alır."""
    global _resolved
    if _forced:
        return _forced
    if _resolved is None:
        _resolved = _detect()
    return _resolved


def _detect() -> str:
    configured = _configured_language()
    if configured in SUPPORTED:
        return configured

    env = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    return "tr" if env.lower().startswith("tr") else "en"


def _configured_language() -> str | None:
    """Config dosyasındaki `ui_language` değerini okur.

    `config` modülü bu modülü içe aktardığı için buradan `config_path`
    çağrılamaz (döngü); dosya yolu aynı kuralla yerinde kurulur. Dosya bozuksa
    dil tespiti sessizce ortam değişkenlerine düşer — hatayı `load_config`
    kullanıcıya zaten gösterecektir.
    """
    from .platforms import config_home

    path = config_home() / "pakize" / "config.toml"
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return None

    value = data.get("ui_language")
    return str(value).lower() if value else None


def _(text: str) -> str:
    """Metni etkin arayüz diline çevirir; kaynak dil Türkçedir."""
    return in_language(text, language())


def in_language(text: str, lang: str) -> str:
    """Metni belirtilen dile çevirir.

    Arayüz dilinden bağımsızdır: seslendirilen anonslar, CLI'ın diline değil
    okunan sesin diline uyar. Katalogda karşılığı olmayan diller İngilizceye
    düşer — Türkçe bir cümlenin Almanca sesle okunması, İngilizcesinden kötüdür.

    Metin zaten İngilizceye çevrilmiş olabilir (bir hata mesajı gibi); Türkçe
    istendiğinde katalog tersten okunur. Tersi bulunmayan metin olduğu gibi
    kalır.
    """
    if lang == "tr":
        return _TR.get(text, text)
    return _EN.get(text, text)


def voice_language(voice: str) -> str:
    """Ses adının dil kodunu döner: "de-AT-IngridNeural" → "de".

    Ses adı zaten dili taşıdığı için ayrı bir "dil" ayarı tutmayız; tek
    doğruluk kaynağı `voice` alanıdır.
    """
    if not voice:
        return "tr"
    return voice.split("-")[0].lower()


_EN: dict[str, str] = {
    # --- genel / komut yardımları ---
    "Metni ses dosyasına çevirir; kod bloklarını okumaz.":
        "Converts text to speech; skips code blocks.",
    "Bir metni seslendirir.": "Reads a text aloud.",
    "Bir kitabı bölüm bölüm seslendirir. Var olan bölümler atlanır; "
    "yarıda kalan iş aynı komutla kaldığı yerden devam eder.":
        "Narrates a book chapter by chapter. Existing chapters are skipped; "
        "an interrupted run resumes with the same command.",
    "Çalmakta olan seslendirmeyi duraklatır; duraklatılmışsa sürdürür.":
        "Pauses the current playback; resumes it if already paused.",
    "Çalmakta olan seslendirmeyi durdurur.": "Stops the current playback.",
    "Çalan seslendirmeyi keser; sıradaki başlar.":
        "Cuts the current playback; the next one in the queue starts.",
    "En son üretilen ses dosyasını yeniden çalar.":
        "Replays the most recently produced audio file.",
    "Edge motorunun sunduğu sesleri listeler.":
        "Lists the voices offered by the Edge engine.",
    "Kurulum sihirbazı: dil ve ses seç, örneğini dinle, config'e yaz.":
        "Setup wizard: pick a language and voice, hear a sample, save to config.",
    "Etkin ayarları gösterir; 'set' alt komutu ile değiştirir.":
        "Shows the effective settings; change them with the 'set' subcommand.",
    "Bir ayarı config dosyasına yazar; dosya yoksa oluşturur.":
        "Writes one setting to the config file; creates the file if missing.",
    "Etkin ayarları ve config dosyasının yolunu gösterir.":
        "Shows the effective settings and the config file path.",
    # --- seçenek yardımları ---
    "Okunacak metin dosyası. Verilmezse stdin'den okunur.":
        "Text file to read. Falls back to stdin when omitted.",
    "Metni panodan al.": "Take the text from the clipboard.",
    "Metni bu dizinin Claude Code oturum kaydından al.":
        "Take the text from this directory's Claude Code session transcript.",
    "Transkriptten kaç söz sırası okunsun. 0 = tamamı.":
        "How many turns to read from the transcript. 0 = all.",
    "Transkriptte hangi konuşmacılar okunsun.":
        "Which speakers to read from the transcript.",
    "Belirli bir oturum kaydı dosyası (varsayılan: en yenisi).":
        "A specific session transcript file (default: the newest).",
    "Üretilecek ses dosyasının yolu.": "Path of the audio file to produce.",
    "TTS sesi.": "TTS voice.",
    "Konuşma hızı çarpanı (örn. 1.15).": "Speech rate multiplier (e.g. 1.15).",
    "Konuşma hızı çarpanı.": "Speech rate multiplier.",
    "Kullanılacak motor.": "Engine to use.",
    "Seslendirmeden önce bu dile çevir (örn. tr, en).":
        "Translate into this language before speaking (e.g. tr, en).",
    "Seslendirmeden önce bu dile çevir (örn. tr).":
        "Translate into this language before speaking (e.g. tr).",
    "Ses hazır olunca otomatik çal.": "Play automatically when the audio is ready.",
    "Parçaları hazır oldukça çal; hepsinin bitmesini bekleme.":
        "Play chunks as they become ready; don't wait for all of them.",
    "Ses üretmeden neyin okunacağını göster.":
        "Show what would be read without producing audio.",
    "Seslendirilecek kitap (.txt, .md, .epub, .pdf, .mobi ...).":
        "Book to narrate (.txt, .md, .epub, .pdf, .mobi ...).",
    "Bölümlerin yazılacağı dizin.": "Directory to write the chapters into.",
    "Bu seviyeye kadar başlıklar bölüm sayılır (1 = yalnızca '#').":
        "Headings up to this level count as chapters (1 = only '#').",
    "Var olan bölümleri de yeniden üret.": "Regenerate existing chapters too.",
    "Ses üretmeden bölüm listesini göster.":
        "Show the chapter list without producing audio.",
    "Çalmak yerine son üretilen sesleri listele.":
        "List recent recordings instead of playing.",
    "Listelenecek kayıt sayısı.": "Number of recordings to list.",
    "Dil ön eki (örn. de, en-US); tümü için: all. Verilmezse özet görünüm.":
        "Language prefix (e.g. de, en-US); use 'all' for everything. "
        "Omit for the overview.",
    "Varsayılan ayarlarla açıklamalı bir config dosyası oluştur.":
        "Create an annotated config file with the default settings.",
    "Ayar adı (örn. voice, rate, translate_to).":
        "Setting name (e.g. voice, rate, translate_to).",
    "Yazılacak yeni değer.": "New value to write.",
    "AYAR": "SETTING",
    "DEĞER": "VALUE",
    # --- speak / book akışı ---
    "Durduruldu.": "Stopped.",
    "Hata: {error}": "Error: {error}",
    "Ses hatası: {error}": "Audio error: {error}",
    "Hazır: {path}": "Ready: {path}",
    "Not: {primary} motoru çalışmadı, {used} kullanıldı.":
        "Note: the {primary} engine failed, {used} was used instead.",
    "Üretilen bölümler korundu; aynı komutu tekrar çalıştırınca kaldığı "
    "yerden devam eder.":
        "Produced chapters are kept; rerunning the same command resumes "
        "where it left off.",
    "Durduruldu. Aynı komutla kaldığı yerden devam edebilirsin.":
        "Stopped. You can resume with the same command.",
    "{count} bölüm zaten üretilmişti, atlandı.":
        "{count} chapters already existed and were skipped.",
    "Hazır: {count} bölüm → {directory}": "Ready: {count} chapters → {directory}",
    "Oynatma listesi: {path}": "Playlist: {path}",
    "Okunmadı: {parts}": "Not read: {parts}",
    "Seslendiriliyor: {done}/{total} parça": "Synthesizing: {done}/{total} chunks",
    "{count} parça, toplam {chars} karakter okunacak.":
        "{count} chunks, {chars} characters will be read in total.",
    "--- parça {number} ---": "--- chunk {number} ---",
    "Bir dosya yolu ver, --clipboard/--transcript kullan ya da metni "
    "stdin'den aktar.":
        "Give a file path, use --clipboard/--transcript, or pipe the text "
        "via stdin.",
    "Girdi boş.": "The input is empty.",
    "Pano boş.": "The clipboard is empty.",
    "Transkriptte okunacak bir konuşma bulunamadı.":
        "No speech to read was found in the transcript.",
    "İpucu: dil ve ses seçimi için 'pakize setup' (bir kez yeter).":
        "Hint: run 'pakize setup' once to pick a language and voice.",
    "Aynı metin zaten sırada; bu basış yok sayıldı.":
        "The same text is already queued; this press was ignored.",
    "Sonrakine geçildi": "Skipped to the next one",
    "İşaret sesi çalınamadı: {error}": "Could not play the cue tone: {error}",
    # --- pause / stop / replay ---
    "Çalan bir seslendirme yok.": "No speech is playing.",
    "Devam ediyor": "Resumed",
    "Duraklatıldı": "Paused",
    "Durduruldu": "Stopped",
    "Sürdürülecek bir çalma yok.": "No playback to resume.",
    "Duraklatılacak bir çalma yok.": "No playback to pause.",
    "Seslendirme zaten sonlanmış.": "The playback had already ended.",
    "({count} seslendirme)": "({count} playbacks)",
    "{directory} içinde ses dosyası yok.": "No audio files in {directory}.",
    "Çalınıyor: {path}": "Playing: {path}",
    # --- voices / setup ---
    "{language} için ses bulunamadı.": "No voices found for {language}.",
    "Seçmek için: pakize config set voice {name}":
        "To select it: pakize config set voice {name}",
    "── {language} (aktif ses: {voice}) ──":
        "── {language} (active voice: {voice}) ──",
    "  ← aktif": "  ← active",
    "── Diğer diller (ayrıntı için: pakize voices -l de) ──":
        "── Other languages (details: pakize voices -l de) ──",
    "{code:<8} {name:<32} {count} ses": "{code:<8} {name:<32} {count} voices",
    "Ses seçimi için sihirbaz: pakize setup":
        "Voice selection wizard: pakize setup",
    "Ses listesi alınamadı: {error}": "Could not fetch the voice list: {error}",
    "Diller:": "Languages:",
    "Dil kodu": "Language code",
    "Tanınmayan dil kodu: {code!r}": "Unknown language code: {code!r}",
    "Numara: örneği dinle • s+numara: seç (örn. s2) • q: çık":
        "Number: hear a sample • s+number: select (e.g. s2) • q: quit",
    "Bir şey yazılmadı.": "Nothing was written.",
    "Geçersiz seçim: {choice!r}": "Invalid choice: {choice!r}",
    "Başka dildeki metinleri bu dile çevirtmek istersen: "
    "pakize config set translate_to {lang}":
        "To have texts in other languages translated into this one: "
        "pakize config set translate_to {lang}",
    "Örnek hazırlanıyor...": "Preparing the sample...",
    "Örnek üretilemedi: {error}": "Could not produce the sample: {error}",
    "Uyarı: ses listesine ulaşılamadı, ad doğrulanmadan yazılıyor.":
        "Warning: the voice list is unreachable; writing the name unvalidated.",
    "Ses bulunamadı: {name!r}": "Voice not found: {name!r}",
    "Benzer adlar: {names}": "Similar names: {names}",
    "Tüm liste için: pakize voices -l all":
        "For the full list: pakize voices -l all",
    # --- config göster / init / set ---
    "Config dosyası: {path}": "Config file: {path}",
    " (yok)": " (missing)",
    "Motor          : {engine} (tanınanlar: {known})":
        "Engine          : {engine} (known: {known})",
    "Yedek motor    : {engine}": "Fallback engine : {engine}",
    "Ses            : {voice}": "Voice           : {voice}",
    "Hız            : {rate} ({percent})": "Rate            : {rate} ({percent})",
    "Parça sınırı   : {count} karakter": "Chunk limit     : {count} characters",
    "Çıktı dizini   : {path}": "Output directory: {path}",
    "Arayüz dili    : {language}": "UI language     : {language}",
    "(sistemden) {lang}": "(from system) {lang}",
    "Akıcı çalma    : {state}": "Streaming play  : {state}",
    "Ondalık düzelt : {state}": "Decimal fix     : {state}",
    "açık": "on",
    "kapalı": "off",
    "Politika:": "Policy:",
    "Dosya zaten var: {path}\n"
    "Üzerine yazmıyorum; değiştirmek istersen dosyayı elle düzenle.":
        "The file already exists: {path}\n"
        "Not overwriting; edit the file by hand if you want to change it.",
    "Yazıldı: {path}": "Written: {path}",
    "Yazıldı: {key} = {value}": "Written: {key} = {value}",
    "Bilinmeyen motor: {value!r} (tanınanlar: {known})":
        "Unknown engine: {value!r} (known: {known})",
    "ui_language için tr veya en bekleniyor: {value!r}":
        "ui_language expects tr or en: {value!r}",
    "Bilinmeyen ayar: {key!r} (geçerli: {valid_keys})":
        "Unknown setting: {key!r} (valid: {valid_keys})",
    "{key} için true/false bekleniyor: {value!r}":
        "{key} expects true/false: {value!r}",
    "{key} için geçersiz değer: {value!r} ({type} bekleniyor)":
        "Invalid value for {key}: {value!r} (expected {type})",
    "Bilinmeyen segment tipi: {type!r}": "Unknown segment type: {type!r}",
    "{type} için bilinmeyen eylem: {action!r} (geçerli: read, announce, skip)":
        "Unknown action for {type}: {action!r} (valid: read, announce, skip)",
    # --- üretilen config dosyası ---
    "# Pakize yapılandırması": "# Pakize configuration",
    "# 'pakize config --init' ile üretildi.":
        "# Generated by 'pakize config --init'.",
    "# Bu dosyayı silersen Pakize varsayılanlarla çalışmaya devam eder.":
        "# If you delete this file Pakize keeps working with the defaults.",
    '# Her segment tipi için: "read" (oku), "announce" (anons et), '
    '"skip" (atla)':
        '# For each segment type: "read", "announce", or "skip"',
    "kullanılacak ses — 'pakize voices' ile listele":
        "voice to use — list them with 'pakize voices'",
    "birincil TTS motoru": "primary TTS engine",
    "birincil motor çalışmazsa denenecek motor":
        "engine to try when the primary one fails",
    "konuşma hızı çarpanı; 1.0 = normal, ara değerler serbest (1.12 olur)":
        "speech rate multiplier; 1.0 = normal, any value works (1.12 is fine)",
    "ses yüksekliği çarpanı": "volume multiplier",
    "ses perdesi kaydırması (Hz); yalnızca edge motorunda": "pitch shift (Hz); edge engine only",
    "bir TTS isteğine sığdırılacak azami karakter":
        "maximum characters per TTS request",
    "çıktı yolu verilmediğinde seslerin biriktiği dizin":
        "directory where audio accumulates when no output path is given",
    "ilk parça hazır olunca çalmaya başla, hepsini bekleme":
        "start playing when the first chunk is ready, don't wait for all",
    "1.15 → 1,15 (Türkçe'de ondalık ayracı virgüldür)":
        "1.15 → 1,15 (Turkish uses a decimal comma)",
    "arayüz dili (tr/en); boşsa sistem dilinden tespit edilir":
        "interface language (tr/en); detected from the system when empty",
    "seslendirmeden önce çevrilecek dil (örn. tr); boşsa çeviri yok":
        "language to translate into before speaking (e.g. tr); empty = none",
    "kaynak dil; auto ise servis kendisi tespit eder":
        "source language; 'auto' lets the service detect it",
    "Piper ses modelinin (.onnx) yolu": "path of the Piper voice model (.onnx)",
    "piper çalıştırılabiliri; boşsa PATH'te aranır":
        "piper executable; searched on PATH when empty",
    "EMA motorunun ayrı Python ortamındaki yorumlayıcısı; boşsa ema kullanılamaz":
        "Python interpreter of the EMA engine's separate environment; ema unusable when empty",
    "antalia-mini motorunun ayrı Python ortamındaki yorumlayıcısı; boşsa antalia-mini kullanılamaz":
        "Python interpreter of the antalia-mini engine's separate environment; antalia-mini unusable when empty",
    "kod blokları — okunmaz, kısaca anons edilir":
        "code blocks — not read, briefly announced",
    "Markdown tabloları": "Markdown tables",
    "çıplak bağlantı adresleri": "bare URLs",
    "dosya yolları — 'read' yalnızca dosya adını okur":
        "file paths — 'read' reads only the file name",
    "yatay çizgiler": "horizontal rules",
    "satır içi `kod` parçaları": "inline `code` spans",
    "düz metin": "prose",
    "başlıklar": "headings",
    "liste maddeleri": "list items",
    "alıntı blokları": "quote blocks",
    # --- seslendirilen anonslar (arayüz diline değil, sesin diline uyar) ---
    "Burada {count} satırlık bir {language} kod bloğu var.":
        "There is a {count}-line {language} code block here.",
    "Burada {count} satırlık bir kod bloğu var.":
        "There is a {count}-line code block here.",
    "Burada {count} satırlık bir tablo var.":
        "There is a {count}-line table here.",
    "Burada okunmayan bir bölüm var.":
        "There is a section here that was not read.",
    "bir kod parçası": "a code snippet",
    "bir bağlantı": "a link",
    "bir dosya yolu": "a file path",
    # --- segment etiketleri (Okunmadı: satırı) ---
    "kod bloğu": "code block",
    "tablo": "table",
    "bağlantı": "link",
    "dosya yolu": "file path",
    "satır içi kod": "inline code",
    "yatay çizgi": "horizontal rule",
    # --- motorlar / ses / kaynaklar / çeviri ---
    "edge motoru için bir ses adı gerekli":
        "the edge engine needs a voice name",
    "edge-tts seslendirme başarısız: {error}":
        "edge-tts synthesis failed: {error}",
    "edge-tts boş ses dosyası üretti — metin okunabilir içerik içermiyor "
    "olabilir":
        "edge-tts produced an empty audio file — the text may contain "
        "nothing readable",
    "Bilinmeyen motor: {name!r} (tanınanlar: {known})":
        "Unknown engine: {name!r} (known: {known})",
    "piper motoru için ses modeli gerekli. Config'e ekle:\n"
    '  piper_model = "/yol/tr_TR-dfki-medium.onnx"':
        "the piper engine needs a voice model. Add it to the config:\n"
        '  piper_model = "/path/tr_TR-dfki-medium.onnx"',
    "Piper ses modeli bulunamadı: {path}": "Piper voice model not found: {path}",
    "piper seslendirme başarısız: {error}": "piper synthesis failed: {error}",
    "piper boş ses dosyası üretti": "piper produced an empty audio file",
    "piper çalıştırılabiliri yok: {path}": "piper executable missing: {path}",
    "piper bulunamadı. Kurmak için: uv tool install piper-tts\n"
    'Kuruluysa yolunu config\'e yaz: piper_binary = "/yol/piper"':
        "piper not found. To install it: uv tool install piper-tts\n"
        'If installed, put its path in the config: piper_binary = "/path/piper"',
    "rate pozitif olmalı": "rate must be positive",
    # --- ema motoru ---
    "ema motoru için ayrı bir Python ortamı gerekli. Kurmak için:\n"
    "  {venv}\n"
    "  {install}\n"
    "sonra yorumlayıcının yolunu config'e yaz:\n"
    '  ema_python = "{example}"':
        "the ema engine needs a separate Python environment. To set it up:\n"
        "  {venv}\n"
        "  {install}\n"
        "then put the interpreter's path in the config:\n"
        '  ema_python = "{example}"',
    "rate {rate} EMA için geçersiz; {low} ile {high} arasında olmalı":
        "rate {rate} is invalid for EMA; it must be between {low} and {high}",
    "EMA ortamında ({python}) gerekli paketler yok: {error}\n"
    "Ayrı bir ortam açıp paketleri oraya kur:\n"
    "  {venv}\n"
    "  {install}\n"
    "sonra yorumlayıcının yolunu config'e yaz:\n"
    '  ema_python = "{example}"':
        "the EMA environment ({python}) lacks the required packages: {error}\n"
        "Create a separate environment and install them there:\n"
        "  {venv}\n"
        "  {install}\n"
        "then put the interpreter's path in the config:\n"
        '  ema_python = "{example}"',
    "ema-lightning {installed} kurulu; güvenli yükleme için tam olarak "
    "{required} gerekli. Kurmak için:\n  {install}":
        "ema-lightning {installed} is installed; safe loading needs exactly "
        "{required}. To install it:\n  {install}",
    # --- antalia-mini motoru ---
    "antalia-mini motoru için ayrı bir Python ortamı gerekli. Kurmak için:\n"
    "{steps}\n"
    "sonra yorumlayıcının yolunu config'e yaz:\n"
    '  antalia_mini_python = "{example}"':
        "the antalia-mini engine needs a separate Python environment. To set it up:\n"
        "{steps}\n"
        "then put the interpreter's path in the config:\n"
        '  antalia_mini_python = "{example}"',
    "antalia-mini ortamında ({python}) gerekli paketler yok: {error}\n"
    "Ayrı bir ortam açıp paketleri oraya kur:\n"
    "{steps}\n"
    "sonra yorumlayıcının yolunu config'e yaz:\n"
    '  antalia_mini_python = "{example}"':
        "the antalia-mini environment ({python}) lacks the required packages: {error}\n"
        "Create a separate environment and install them there:\n"
        "{steps}\n"
        "then put the interpreter's path in the config:\n"
        '  antalia_mini_python = "{example}"',
    "antalia-mini {installed} kurulu; tam olarak {required} gerekli. "
    "Kurmak için:\n  {install}":
        "antalia-mini {installed} is installed; exactly {required} is required. "
        "To install it:\n  {install}",
    # --- işçi süreçli motorların ortak mesajları (EMA, antalia-mini) ---
    "{key} ile gösterilen Python yok: {path}":
        "the Python pointed to by {key} is missing: {path}",
    "{engine} seslendirme başarısız: {error}": "{engine} synthesis failed: {error}",
    "{engine} boş ses dosyası üretti": "{engine} produced an empty audio file",
    "{engine} işçisi başlatılamadı: {error}":
        "the {engine} worker could not be started: {error}",
    "{engine} işçisi {seconds:.0f} sn içinde hazır olmadı.":
        "the {engine} worker was not ready within {seconds:.0f} s.",
    "{engine} işçisi açılırken kapandı (çıkış kodu {code}).":
        "the {engine} worker exited while starting (exit code {code}).",
    "{engine} işçisi seslendirme sırasında kapandı (çıkış kodu {code}).":
        "the {engine} worker exited during synthesis (exit code {code}).",
    "{engine} işçisi {seconds:.0f} sn içinde yanıt vermedi; kapatıldı.":
        "the {engine} worker did not answer within {seconds:.0f} s; it was shut down.",
    "{engine} model dosyaları indirilemedi (ilk kullanımda ağ gerekir): {error}":
        "the {engine} model files could not be downloaded (first use needs network): {error}",
    "{engine} model dosyası beklenen sha256 ile uyuşmuyor: {file}. "
    "Dosya değişmiş olabilir; model yüklenmedi.":
        "a {engine} model file does not match the expected sha256: {file}. "
        "The file may have changed; the model was not loaded.",
    "{engine} modeli yüklenemedi: {error}": "the {engine} model could not be loaded: {error}",
    "Birleştirilecek ses parçası yok": "No audio chunks to concatenate",
    "ffplay hata verdi (kod {code}): {error}":
        "ffplay failed (code {code}): {error}",
    "{name} bulunamadı. Kurmak için: {hint}":
        "{name} not found. To install it: {hint}",
    "{name} hata verdi (kod {code}): {error}":
        "{name} failed (code {code}): {error}",
    "Seslendirilecek içerik kalmadı — metin tamamen atlanan segmentlerden "
    "oluşuyor olabilir":
        "Nothing left to read — the text may consist entirely of skipped "
        "segments",
    "Dosya bulunamadı: {path}": "File not found: {path}",
    "{suffix} biçimi için {converter} gerekli (Calibre ile gelir): {hint}":
        "The {suffix} format needs {converter} (ships with Calibre): {hint}",
    "{converter} dönüştürme başarısız: {error}":
        "{converter} conversion failed: {error}",
    "Kitapta seslendirilecek metin bulunamadı":
        "No narratable text found in the book",
    "Bölüm bulunamadı.": "No chapters found.",
    "Bölüm {number}": "Chapter {number}",
    "(atlandı)": "(skipped)",
    "Bölüm {number}/{total}: {title}{state}":
        "Chapter {number}/{total}: {title}{state}",
    "{count} bölüm, toplam {chars} karakter.":
        "{count} chapters, {chars} characters in total.",
    "{name:<48} {chars:>8} karakter": "{name:<48} {chars:>8} characters",
    "Pano okunamadı — {errors}": "Could not read the clipboard — {errors}",
    "Pano okunamıyor: pbpaste bulunamadı (macOS ile gelmesi gerekir).":
        "Cannot read the clipboard: pbpaste not found (it ships with macOS).",
    "Pano okunamıyor: PowerShell PATH üzerinde bulunamadı.":
        "Cannot read the clipboard: PowerShell not found on PATH.",
    "Pano okunamıyor: xclip, xsel veya wl-clipboard kurulu değil. "
    "Kurmak için: sudo apt install xclip":
        "Cannot read the clipboard: xclip, xsel or wl-clipboard is not "
        "installed. To install: sudo apt install xclip",
    "araç yanıt vermedi": "the tool did not respond",
    "çıkış kodu {code}": "exit code {code}",
    "{cwd} için Claude Code oturum kaydı bulunamadı (bakılan yer: {looked})":
        "No Claude Code session transcript found for {cwd} (looked in: {looked})",
    "last en az 1 olmalı": "last must be at least 1",
    "max_chars pozitif olmalı": "max_chars must be positive",
    "Çeviri yanıtı anlaşılamadı: {error}":
        "Could not parse the translation response: {error}",
    "Çeviri servisi hata verdi (HTTP {code})":
        "The translation service returned an error (HTTP {code})",
    "Çeviri servisine ulaşılamadı. Ücretsiz uç geçici olarak engellemiş "
    "olabilir; biraz sonra tekrar dene. ({error})":
        "Could not reach the translation service. The free endpoint may have "
        "temporarily blocked us; try again later. ({error})",
    "Çeviri servisi bu bağlantıyı şimdilik kısıtladı (HTTP 429). "
    "Tekrar denemek kısıtlamayı uzatır; bir süre sonra dene.":
        "The translation service has rate-limited this connection for now "
        "(HTTP 429). Retrying extends the limit; try again later.",
    "Çeviri şu an kullanılamıyor. Google kısa bir süreliğine sınır koydu. "
    "Birkaç dakika bekleyip tekrar dene; hemen denersen bekleme uzar.":
        "Translation is unavailable right now. Google has set a temporary "
        "limit. Wait a few minutes and try again; retrying right away makes "
        "the wait longer.",
    "Uyarı sesi çalınamadı: {error}": "Could not play the warning sound: {error}",
    # --- konuşmayı metne çevirme ---
    "Bir ses dosyasındaki konuşmayı metne çevirir.":
        "Transcribes the speech in an audio file.",
    "Metne çevrilecek ses dosyası.": "The audio file to transcribe.",
    "Metnin yazılacağı dosya; yoksa ekrana basar.":
        "File to write the text to; prints to the screen if omitted.",
    "Kullanılacak config dosyası.": "The config file to use.",
    "Ses dosyası bulunamadı: {path}": "Audio file not found: {path}",
    "Kayıtta konuşma bulunamadı.": "No speech found in the recording.",
    "Deşifre için sunucu adresi gerekli. Config'e ekle:\n"
    '  asr_server_url = "http://127.0.0.1:8099"':
        "Transcription needs a server address. Add it to the config:\n"
        '  asr_server_url = "http://127.0.0.1:8099"',
    "Bilinmeyen deşifre motoru: {name!r} (tanınanlar: {known})":
        "Unknown transcription engine: {name!r} (known: {known})",
    "Tanınmayan ses biçimi: {suffix} (tanınanlar: {known})":
        "Unrecognised audio format: {suffix} (known: {known})",
    "Ses dosyası okunamadı: {path} ({reason})":
        "Could not read the audio file: {path} ({reason})",
    "Deşifre sunucusu beklenmedik bir yanıt döndürdü.":
        "The transcription server returned an unexpected response.",
    "Deşifre sunucusu geçerli JSON döndürmedi.":
        "The transcription server did not return valid JSON.",
    "Deşifre sunucusu {code} döndü: {detail}":
        "The transcription server returned {code}: {detail}",
    "Deşifre sunucusuna ulaşılamadı ({url}): {reason}":
        "Could not reach the transcription server ({url}): {reason}",
    "Deşifre sunucusu yanıt vermedi ({url}): {reason}":
        "The transcription server did not respond ({url}): {reason}",
    "Deşifre için bir sunucu gerekli. Config'e ya model yolunu ekle "
    "(Pakize sunucuyu kendisi açıp kapatır):\n"
    '  asr_model = "/yol/model.gguf"\n'
    '  asr_mmproj = "/yol/mmproj.gguf"\n'
    "ya da çalışan bir sunucunun adresini:\n"
    '  asr_server_url = "http://127.0.0.1:8099"':
        "Transcription needs a server. Add the model path to the config "
        "(Pakize starts and stops the server itself):\n"
        '  asr_model = "/path/model.gguf"\n'
        '  asr_mmproj = "/path/mmproj.gguf"\n'
        "or the address of a running server:\n"
        '  asr_server_url = "http://127.0.0.1:8099"',
    "Model sesi okuyabilmek için ses kodlayıcısına ihtiyaç duyar. "
    "Config'e ekle:\n"
    '  asr_mmproj = "/yol/mmproj.gguf"':
        "The model needs its audio encoder to read audio. Add it to the config:\n"
        '  asr_mmproj = "/path/mmproj.gguf"',
    "llama-server bulunamadı. llama.cpp sürümlerinden indirilebilir:\n"
    "  https://github.com/ggml-org/llama.cpp/releases\n"
    'Kuruluysa yolunu config\'e yaz: asr_server_binary = "/yol/llama-server"':
        "llama-server not found. It can be downloaded from the llama.cpp releases:\n"
        "  https://github.com/ggml-org/llama.cpp/releases\n"
        'If installed, set its path in the config: asr_server_binary = "/path/llama-server"',
    "Deşifre sunucusu başlatılamadı: {reason}":
        "Could not start the transcription server: {reason}",
    "Deşifre sunucusu açılırken kapandı (çıkış kodu {code}).":
        "The transcription server exited while starting (exit code {code}).",
    "Deşifre sunucusu {seconds:.0f} sn içinde hazır olmadı.":
        "The transcription server was not ready within {seconds:.0f} s.",
    "{setting} ile gösterilen dosya yok: {path}":
        "The file set by {setting} does not exist: {path}",
    # --- config açıklamaları ---
    "konuşmayı metne çeviren motor": "the speech-to-text engine",
    "dışarıda çalışan deşifre sunucusu; boşsa asr_model ile Pakize başlatır":
        "an externally run transcription server; if empty, Pakize starts one from asr_model",
    "deşifre modeli (.gguf); sunucu her iş için açılıp kapanır":
        "transcription model (.gguf); the server starts and stops for each job",
    "modelin ses kodlayıcısı (mmproj .gguf)": "the model's audio encoder (mmproj .gguf)",
    "llama-server çalıştırılabiliri; boşsa PATH'te aranır":
        "llama-server executable; searched on PATH if empty",
    "terimleri cümle içinde anlatan paragraf; çıplak liste işe yaramaz":
        "a paragraph using the terms in sentences; a bare word list does not help",
    '# Deşifre çıktısında düzeltilecek yazımlar: "yanlış" = "doğru"':
        '# Spellings to fix in the transcript: "wrong" = "right"',
    "# Yalnız bütün kelime eşleşir; büyük-küçük harf ayrı sayılır.":
        "# Only whole words match; upper and lower case are distinct.",
    "[asr_replacements] içinde boş anahtar var.":
        "[asr_replacements] contains an empty key.",
    "[asr_replacements] içinde {key!r} için metin bekleniyor.":
        "[asr_replacements] expects text for {key!r}.",
    "bir deşifre isteğinin azami süresi (saniye)":
        "maximum duration of a transcription request (seconds)",
    # --- dikte ---
    "Konuşmayı kaydedip metne çevirir ve panoya koyar; "
    "ikinci çağrı kaydı bitirir.":
        "Records speech, transcribes it and puts the text on the clipboard; "
        "a second call ends the recording.",
    "Metni panoya koy.": "Put the text on the clipboard.",
    "Kayıt bitiriliyor.": "Finishing the recording.",
    "Kayıt zaten bitti; deşifre sürüyor.":
        "The recording has already ended; transcription is in progress.",
    "Kayıt başladı. Bitirmek için komutu tekrar çalıştır (terminalde Ctrl+C).":
        "Recording. Run the command again to finish (Ctrl+C in a terminal).",
    "Deşifre ediliyor...": "Transcribing...",
    "Dikte başarısız oldu.": "Dictation failed.",
    "dictate_{name}_sound ile gösterilen dosya yok: {path}":
        "The file set by dictate_{name}_sound does not exist: {path}",
    "Windows'ta mikrofon adı gerekli. Aygıtları listele:\n"
    "  ffmpeg -list_devices true -f dshow -i dummy\n"
    "sonra config'e yaz:\n"
    '  dictate_microphone = "dshow:audio=Mikrofon (Realtek Audio)"':
        "Windows needs the microphone's name. List the devices:\n"
        "  ffmpeg -list_devices true -f dshow -i dummy\n"
        "then set it in the config:\n"
        '  dictate_microphone = "dshow:audio=Microphone (Realtek Audio)"',
    "dictate_microphone 'biçim:aygıt' şeklinde olmalı "
    "(örn. pulse:default, avfoundation::0): {value!r}":
        "dictate_microphone must be 'format:device' "
        "(e.g. pulse:default, avfoundation::0): {value!r}",
    "Kayıt başlatılamadı: {reason}": "Could not start recording: {reason}",
    "Kayıt başarısız oldu (ffmpeg çıkış kodu {code}).":
        "Recording failed (ffmpeg exit code {code}).",
    "Kayıt boş: mikrofondan ses gelmedi.":
        "The recording is empty: no audio came from the microphone.",
    "Panoya yazılamadı — {errors}": "Could not write to the clipboard — {errors}",
    # --- fix ---
    "Deşifre düzeltme tablosuna bir satır yazar: yanlış yazım → doğrusu. "
    "Dikte bir kelimeyi hep yanlış yazıyorsa buraya.":
        "Writes one line to the transcription correction table: wrong spelling → right one. "
        "For words dictation keeps getting wrong.",
    "YANLIŞ": "WRONG",
    "DOĞRU": "RIGHT",
    "Deşifrenin yazdığı biçim.": "The form the transcription produces.",
    "Yerine yazılacak biçim.": "The form to write instead.",
    "Tabloyu göster.": "Show the table.",
    "YANLIŞ için satırı sil.": "Remove the line for WRONG.",
    "Düzeltme tablosu boş.": "The correction table is empty.",
    "Kullanım: pakize fix YANLIŞ DOĞRU  (örn. pakize fix rümut remote)":
        "Usage: pakize fix WRONG RIGHT  (e.g. pakize fix rümut remote)",
    "Silindi: {key}": "Removed: {key}",
    "Tabloda yok: {key}": "Not in the table: {key}",
    "Yazıldı: {wrong} → {right}": "Written: {wrong} → {right}",
    "Değişti: {wrong} → {right} (önce: {previous})":
        "Changed: {wrong} → {right} (was: {previous})",
    "Yanlış ve doğru yazım boş olamaz.": "Neither the wrong nor the right spelling can be empty.",
    # --- dikte config açıklamaları ---
    "dikte mikrofonu, ffmpeg biçim:aygıt yazımıyla; boşsa sistem varsayılanı":
        "dictation microphone in ffmpeg's format:device form; system default if empty",
    "bir diktenin azami kayıt süresi (saniye)":
        "maximum recording length of one dictation (seconds)",
    "kayıt başlarken çalınan ses; boşsa üretilen ton":
        "sound played when recording starts; a generated tone if empty",
    "kayıt bitince çalınan ses; boşsa üretilen ton":
        "sound played when recording ends; a generated tone if empty",
    "metin panoya konunca çalınan ses; boşsa üretilen ton":
        "sound played when the text is on the clipboard; a generated tone if empty",
    "dikte başarısız olunca çalınan ses; boşsa üretilen ton":
        "sound played when dictation fails; a generated tone if empty",
}
"""Türkçe → İngilizce kataloğu.

Eksik girdi Türkçeye düşer; `tests/test_i18n.py` kaynaktaki her `_()`
çağrısının burada karşılığı olduğunu doğrular.
"""

_TR: dict[str, str] = {english: turkish for turkish, english in _EN.items()}
"""İngilizce → Türkçe; `in_language` zaten çevrilmiş bir metni geri almak için."""
