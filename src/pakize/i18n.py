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
    """
    if lang == "tr":
        return text
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
    "ses perdesi kaydırması (Hz)": "pitch shift (Hz)",
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
}
"""Türkçe → İngilizce kataloğu.

Eksik girdi Türkçeye düşer; `tests/test_i18n.py` kaynaktaki her `_()`
çağrısının burada karşılığı olduğunu doğrular.
"""
