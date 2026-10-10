[English](README.en.md) · **Türkçe**

# Pakize

[![CI](https://github.com/mustafa-kahraman/pakize/actions/workflows/ci.yml/badge.svg)](https://github.com/mustafa-kahraman/pakize/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pakize?logo=pypi&logoColor=white)](https://pypi.org/project/pakize/)

**Tanıtım — 29 saniye, sesi aç:**

https://github.com/user-attachments/assets/c1f04038-855b-4624-be39-a584f3a0d7a5

> Videodaki anlatımı Pakize'nin kendisi üretti; altyazılar gömülü.

Metni ses dosyasına çeviren yerel araç. Markdown'ı anlar: **kod bloklarını
okumaz**, yerlerine kısa bir anons koyar; tabloları, bağlantıları ve biçim
işaretlerini de politikaya göre eler.

- **Kaynaklar** — dosya, pano, stdin ya da Claude Code oturum kaydı
- **Kitap** — EPUB/PDF/MOBI'yi bölüm bölüm seslendirir, yarıda kalırsa devam eder
- **Çeviri** — seslendirmeden önce hedef dile çevirir
- **Motorlar** — edge-tts (çevrimiçi, kaliteli), ağ yoksa Piper'a düşer; tamamen yerel Türkçe için EMA
- **Denetim** — klavye kısayoluyla oku, duraklat, durdur
- **Dikte** — konuş, tuşa bas, metin panoda; tanıma yerel modelle, ağ gerekmez
- **Platformlar** — Linux, macOS ve Windows

> **Resmî olmayan servisler.** Pakize sesi `edge-tts` üzerinden Microsoft'un
> Edge "Read Aloud" ucundan, çeviriyi Google'ın ücretsiz çeviri ucundan alır.
> İkisi de **belgelenmiş, resmî olarak desteklenen API'ler değildir**: kota
> belirsizdir, herhangi bir zaman değişebilir ya da kapanabilir ve ilgili
> şirketlerin kullanım şartları üçüncü taraf kullanımını öngörmez. Kişisel
> kullanım için düşünülmüştür; ticari ya da yoğun kullanım öncesinde bunu
> değerlendirmek sana düşer. Ağ gerektirmeyen tam yerel bir alternatif için
> [Piper](#çevrimdışı-yedek-piper) ve [EMA](#çevrimdışı-türkçe-motor-ema-lightning)
> bölümlerine bak.

## Kurulum

Linux, macOS ve Windows'ta aynı dört adım. Üçünde de yaklaşık beş dakika sürer.

**Python'u ayrıca kurmana gerek yok** — uv, gerekirse uygun sürümü kendisi
indirir.

### 1. uv'yi kur

[uv](https://docs.astral.sh/uv/), Python araçlarını kuran ve çalıştıran
programdır. Zaten varsa bu adımı atla (`uv --version` ile bak).

**Linux / macOS** — terminalde:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows** — PowerShell'de:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Kurulum bittikten sonra **terminali kapatıp yeniden aç**; `uv` ancak o zaman
tanınır.

### 2. ffmpeg'i kur

Pakize sesi ffmpeg ile birleştirir ve çalar; onsuz çalışmaz.

**Linux:**

```bash
sudo apt install ffmpeg
```

**macOS** ([Homebrew](https://brew.sh) ile):

```bash
brew install ffmpeg
```

**Windows** (PowerShell'de):

```powershell
winget install Gyan.FFmpeg
```

> Windows'ta winget kurulumdan sonra PATH'i günceller ama **açık olan
> terminaller bunu görmez**. Yeni bir PowerShell aç ve `ffmpeg -version` ile
> doğrula.

### 3. Pakize'yi kur

```bash
uv tool install pakize
```

Paketi [PyPI'den](https://pypi.org/project/pakize/) indirir; depoyu klonlamana
gerek yoktur.

**Geliştirmek için depodan kuruyorsan** — proje dizininde:

```bash
uv tool install --editable .
```

`--editable`, depoda yaptığın değişikliklerin anında geçerli olmasını sağlar;
her değişiklikte yeniden kurman gerekmez.

Bu komut `pakize` çalıştırılabilirini uv'nin araç dizinine koyar — Linux ve
macOS'ta `~/.local/bin/pakize`, Windows'ta
`%USERPROFILE%\.local\bin\pakize.exe`.

### 4. Doğrula

`pakize` komutu tanınmıyorsa araç dizini PATH'te değildir:

```bash
uv tool update-shell
```

Sonra terminali yeniden aç. Kurulumun çalıştığını gör:

```bash
pakize config
```

Etkin ayarları ve dosya yollarını yazdırır. Gerçek bir deneme (internet ister):

```bash
echo "Merhaba, ben Pakize." | pakize speak
```

Ses duyuyorsan kurulum tamamdır.

Kaldırmak için: `uv tool uninstall pakize`.

### Güncelleme

PyPI'den kurduysan:

```bash
uv tool upgrade pakize
```

**Depodan kurduysan `git pull` tek başına yetmez.** `--editable` kurulumda kod
anında güncellenir ama bağımlılık listesi değiştiyse araç ortamı eski kalır ve
şuna benzer bir hata alırsın:

```
ModuleNotFoundError: No module named 'psutil'
```

Yeniden kurmak yeterli — `--force`, var olan kurulumun üzerine yazar:

```bash
uv tool install --editable . --force
```

### İsteğe bağlı araçlar

Yukarıdakiler temel kullanım için yeter. Şu özellikleri kullanacaksan
karşılarındaki aracı da kur:

| Araç | Ne için | Linux | macOS | Windows |
|------|---------|-------|-------|---------|
| `calibre` | EPUB/PDF/MOBI seslendirme | `sudo apt install calibre` | `brew install --cask calibre` | `winget install calibre.calibre` |
| pano aracı | `--clipboard` | `sudo apt install xclip` | sistemle gelir (`pbpaste`) | sistemle gelir (PowerShell) |
| `piper` | çevrimdışı yedek motor | `uv tool install piper-tts` | aynı | aynı |
| EMA ortamı | çevrimdışı Türkçe motor `ema` | bkz. [EMA](#çevrimdışı-türkçe-motor-ema-lightning) | aynı | aynı |

Pakize eksik bir araçla karşılaştığında **bulunduğun platformun** kurulum
komutunu söyler; hata mesajındaki komutu olduğu gibi çalıştırabilirsin.

### Paketleme

Başkasına göndermek üzere dağıtılabilir paket üretmek için:

```bash
uv build          # dist/ altına .whl ve .tar.gz yazar
```

Bu, internetsiz bir makineye kurulum için işe yarar; normal şartlarda karşı
taraf `uv tool install pakize` demeyi tercih eder. Dosyayı alan kişi, yolunu
vererek kurar:

```bash
uv tool install /yol/pakize-0.5.2-py3-none-any.whl
```

Paket yalnızca Python bağımlılıklarını taşır; `ffmpeg` ve isteğe bağlı araçlar
her makinede ayrıca gerekir.

## Kullanım

```bash
# Dosyadan
pakize speak notlar.md

# Panodan
pakize speak --clipboard

# Claude Code'un bu dizindeki son cevabından
pakize speak --transcript

# Borudan
echo "Okunacak metin" | pakize speak

# Ses üretmeden neyin okunacağını gör
pakize speak notlar.md --dry-run

# Belirli bir dosyaya yaz, otomatik çalma
pakize speak notlar.md -o cikti.mp3 --no-play
```

> Sisteme kurmadıysan komutların başına `uv run` ekle ve proje dizininden çalıştır.

Çıktı yolu verilmezse ses, sistemin geçici dizini altına `<tarih-saat>.mp3`
olarak yazılır ve hemen çalmaya başlar — Linux'ta `/tmp/pakize/`, Windows'ta
`%TEMP%\pakize\`, macOS'ta oturuma özel `/var/folders/.../pakize/`. Etkin yolu
`pakize config` gösterir.

Sesler orada birikir; ileride lazım olan bir kaydı oradan alabilirsin. Geçici
dizin yeniden başlatmada temizlendiği için kalıcı arşiv istiyorsan `output_dir`
ayarını değiştir.

### Bayraklar

| Bayrak | Açıklama |
|--------|----------|
| `-c, --clipboard` | Metni panodan al |
| `-t, --transcript` | Metni Claude Code oturum kaydından al |
| `-n, --last` | Transkriptten kaç söz sırası okunsun (0 = tamamı) |
| `--roles` | `assistant` (varsayılan), `user` veya `all` |
| `--session` | Belirli bir oturum kaydı dosyası |
| `-o, --output` | Üretilecek ses dosyasının yolu |
| `-v, --voice` | TTS sesi (örn. `tr-TR-AhmetNeural`) |
| `-r, --rate` | Konuşma hızı çarpanı (örn. `1.15`) |
| `-e, --engine` | Kullanılacak motor |
| `-T, --translate` | Seslendirmeden önce bu dile çevir (örn. `tr`) |
| `--no-play` | Ses hazır olunca otomatik çalma |
| `--no-stream` | Parçaları beklet, hepsi bitince tek seferde çal |
| `--dry-run` | Ses üretmeden okunacak metni göster |

### Diğer komutlar

```bash
pakize book kitap.epub        # bir kitabı bölüm bölüm seslendir
pakize dictate                # dikte: kaydet, metne çevir, panoya koy (ikinci çağrı bitirir)
pakize transcribe kayit.wav   # bir ses dosyasındaki konuşmayı metne çevir
pakize fix rümut remote       # dikte hep yanlış yazıyorsa: düzeltme tablosuna satır ekle
pakize pause                  # çalmayı duraklat; duraklatılmışsa sürdür (aynı komut)
pakize stop                   # çalanı atla; sıradaki varsa başlar
pakize stop --all             # çalanı ve sırada bekleyenleri durdur
pakize replay                 # en son üretilen sesi yeniden çal
pakize replay --list          # son üretilen sesleri tarihiyle listele
pakize replay --list -n 30    # daha fazlasını göster
pakize setup                  # sihirbaz: dil ve ses seç, örneğini dinle
pakize voices                 # aktif dilin sesleri + diğer dillerin özeti
pakize voices -l de           # bir dilin seslerini listele
pakize voices -l all          # tüm sesleri listele
pakize config                 # etkin ayarları göster
pakize config --init          # açıklamalı config dosyası oluştur
pakize config set voice de-AT-IngridNeural   # bir ayarı dosyaya yaz
```

## Çeviri

Metni seslendirmeden önce çevirir. İngilizce bir kitabı Türkçe dinlemek için:

```bash
pakize speak makale.md --translate tr    # veya -T tr
pakize book kitap.epub --translate tr
pakize speak -t -T en                    # son cevabı İngilizce dinle
```

Kaynak dil kendiliğinden tespit edilir; zaten hedef dildeyse metne dokunulmaz.
Kalıcı hâle getirmek için: `pakize config set translate_to tr`.

### Nereye yerleşiyor

Çeviri, **ayrıştırmadan sonra ve politikadan önce** çalışır. Sırası önemli:

| Adım | Neden |
|------|-------|
| Ayrıştırmadan sonra | Kod blokları ve tablolar çeviriye hiç girmez |
| Politikadan önce | "Burada 12 satırlık bir kod bloğu var" anonsu tekrar çevrilmez |

Çevrilen segmentler: düz metin, başlık, liste maddesi, alıntı. Kod, tablo,
bağlantı ve dosya yolları dokunulmadan geçer.

Örnek — İngilizce kaynak, Türkçe çıktı:

```
Elliott Dalganın Temelleri.
Elliott Wave teorisi, piyasa fiyatlarının belirli kalıplarda ortaya çıktığını
öne sürüyor.
Burada 2 satırlık bir Python kod bloğu var.     ← kod çevrilmedi, anons Türkçe
İkinci dalga hiçbir zaman birinci dalganın yüzde 100'ünden fazlasını geri
çekemez.
```

### Sınırlar

Google'ın ücretsiz ucu **resmî bir API değildir**: kota belirsizdir ve çok
sayıda istekte geçici olarak engellenebilir.

Bunu hafifletmek için satırlar toplu gönderilir — uç satır sonlarını koruduğu
için tek istekte onlarca segment çevrilir. Bir kitapta bu, binlerce istek
yerine yüzlerce istek demektir. İstekler seri gider, aralarında kısa bir
bekleme olur ve hız sınırında artan gecikmeyle tekrar denenir.

Yine de engellenirsen: kitap seslendirmede üretilen bölümler korunur, biraz
sonra aynı komutu çalıştırınca kaldığı yerden devam eder.

## Kitap seslendirme

Uzun bir metni bölüm bölüm sese çevirir. Bir kitap 8-10 saatlik ses demek;
tek dosya yerine her bölüm ayrı yazılır, yanına oynatma listesi bırakılır.

```bash
pakize book kitap.epub                  # bölümler geçici dizindeki kitap/ altına
pakize book kitap.pdf -o ~/Müzik/kitap  # başka bir dizine
pakize book kitap.md --dry-run          # bölüm listesini gör, ses üretme
pakize book kitap.epub -l 1             # yalnızca '#' başlıkları bölüm sayılsın
```

Çıktı:

```
kitap/
  01-onsoz.mp3
  02-birinci-bolum.mp3
  03-ikinci-bolum.mp3
  kitap.m3u
```

### Yarıda kalırsa

Var olan bölüm dosyaları yeniden üretilmez. Üretim kesilirse (ağ koptu, Ctrl+C
bastın, makine kapandı) **aynı komutu tekrar çalıştır** — kaldığı yerden devam
eder:

```
Bölüm 1/24: Önsöz (atlandı)
Bölüm 2/24: Birinci Bölüm (atlandı)
Bölüm 3/24: İkinci Bölüm
```

Sıfır baytlık dosyalar yarım kalmış sayılır ve yeniden üretilir. Her şeyi
baştan üretmek için `--force`.

### Desteklenen biçimler

`.txt` ve `.md` doğrudan okunur. `.epub`, `.pdf`, `.mobi` ve Calibre'nin
tanıdığı diğer biçimler `ebook-convert` ile Markdown'a çevrilir:

```bash
sudo apt install calibre           # Linux
brew install --cask calibre        # macOS
winget install calibre.calibre     # Windows
```

> macOS ve Windows'ta Calibre kendini PATH'e eklemeyebilir. `ebook-convert`
> bulunamıyorsa macOS'ta `/Applications/calibre.app/Contents/MacOS`,
> Windows'ta `C:\Program Files\Calibre2` dizinini PATH'e ekle.

Markdown istenmesinin sebebi başlıkların korunması — bölüm ayrımının tek
güvenilir kaynağı onlar.

> PDF'te metin katmanı yoksa (taranmış kitap) ya da sayfa düzeni çok sütunluysa
> dönüştürme kalitesi düşer. `--dry-run` ile bölüm listesine bakıp karar ver.

### Bölüm bulunamazsa

Metinde hiç başlık yoksa kitap, paragraf sınırlarına saygı duyularak yaklaşık
eşit parçalara bölünür — aksi hâlde tüm kitap tek devasa dosyaya düşerdi.

## Claude Code transkripti

Kopyala-yapıştır gerekmeden, o dizindeki son Claude Code cevabını dinle:

```bash
pakize speak --transcript      # son cevap
pakize speak -t -n 3           # son 3 söz sırası
pakize speak -t --roles all    # senin mesajların da okunsun
pakize speak -t -n 0           # oturumun tamamı
```

Oturum kaydı, bulunduğun dizine göre `~/.claude/projects/` altından seçilir;
o projenin en son güncellenmiş oturumu kullanılır. Başka bir kaydı okumak için
`--session /yol/oturum.jsonl`.

### Neyin okunduğu

Kayıt dosyasında konuşmanın yanında araç çağrıları ve çıktıları da durur.
Okunan yalnızca konuşmadır:

| Kayıt | Durum |
|-------|-------|
| Asistanın metin blokları | okunur |
| Kullanıcının yazdığı mesajlar | `--roles` ile okunur |
| Düşünme blokları (`thinking`) | atlanır |
| Araç çağrıları ve çıktıları | atlanır |
| Alt ajan (sidechain) konuşmaları | atlanır |
| `<system-reminder>` gibi araç etiketleri | temizlenir |

Tek bir cevap, araya giren araç çağrıları yüzünden onlarca kayda bölünebilir.
Kullanıcı açısından bunların hepsi tek bir yanıt olduğu için ardışık aynı
rolden kayıtlar tek söz sırasında birleştirilir — `-n 1` cevabın tamamını verir,
son cümlesini değil.

`--roles all` seçildiğinde araya kimin konuştuğunu belirten kısa bir ayraç
konur ("Kullanıcı:", "Asistan:"); tek rol okunurken ayraç konmaz.

## Dikte

Pakize ters yönde de çalışır: konuş, tuşa bas, metin panoda. Tanıma yerel bir
modelle yapılır; ses makineden çıkmaz, ağ gerekmez.

### Kurulum

İki parça gerekir: llama.cpp'nin sunucusu ve Qwen3-ASR modeli. İkisi de tek
seferlik indirmedir.

1. [llama.cpp sürümlerinden](https://github.com/ggml-org/llama.cpp/releases)
   platformuna uyan arşivi indir; içinden `llama-server` yeter.
2. [Qwen3-ASR-1.7B-GGUF](https://huggingface.co/ggml-org/Qwen3-ASR-1.7B-GGUF)
   sayfasından model dosyasını (`Qwen3-ASR-1.7B-Q8_0.gguf`) ve ses kodlayıcısını
   (`mmproj-Qwen3-ASR-1.7B-Q8_0.gguf`) indir.
3. Yollarını config'e yaz:

```bash
pakize config set asr_model ~/.local/share/pakize/asr/Qwen3-ASR-1.7B-Q8_0.gguf
pakize config set asr_mmproj ~/.local/share/pakize/asr/mmproj-Qwen3-ASR-1.7B-Q8_0.gguf
pakize config set asr_server_binary ~/.local/share/pakize/asr/llama-server
```

`llama-server` `PATH` üzerindeyse son satır gerekmez. Mikrofon kaydını zaten
kurulu olan `ffmpeg` yapar.

Kurulumu bir ses dosyasıyla dene:

```bash
pakize transcribe kayit.wav
```

### Nasıl çalışır

Tek komut, iki basış:

1. `pakize dictate` — yükselen bir ton çalar, kayıt başlar. Deşifre sunucusu
   bu sırada arka planda açılır; modelin yüklenmesi sen konuşurken geçer.
2. `pakize dictate` (tekrar) — kayıt biter, alçalan bir ton çalar, konuşma
   metne çevrilir ve panoya konur; "hazır" tonu metnin panoda olduğunu söyler.
   Sunucu kapanır.

Terminalden çalıştırıyorsan ikinci basış Ctrl+C'dir. Metin panonun yanı sıra
ekrana da basılır; `--no-clipboard` yalnız ekrana basar.

Sürekli dinleyen hiçbir şey yoktur: mikrofon ve sunucu tek bir diktenin ömrü
kadar yaşar. İkinci basış unutulursa kayıt `dictate_max_seconds` (varsayılan
5 dakika) dolunca kendiliğinden biter ve o ana kadarki konuşma çevrilir.

Bir şey ters giderse pes bir ton çalar ve Pakize hatayı kendi sesiyle okur:
kısayoldan çalışırken ekran yoktur, hatanın tek görünür yeri sestir.

### Tonlar

Varsayılan tonlar ffmpeg ile üretilir; pakette ses dosyası yoktur. Kendi
seslerini kullanmak istersen config'te dosya göster:

```toml
dictate_start_sound = "~/Music/sounds/start.mp3"   # kayıt başlarken
dictate_stop_sound  = "~/Music/sounds/stop.mp3"    # kayıt bitince
dictate_done_sound  = "~/Music/sounds/done.mp3"    # metin panoya konunca
dictate_error_sound = "~/Music/sounds/error.mp3"   # bir şey ters gidince
```

Sıra kasıtlı: başta ton kayıttan önce, sonda kayıttan sonra çalar; aksi hâlde
mikrofon tonun kendisini kaydeder.

### Mikrofon

Linux'ta PulseAudio/PipeWire'ın varsayılan aygıtı, macOS'ta ilk ses aygıtı
kullanılır. Başka bir aygıt için ayar, ffmpeg'in `biçim:aygıt` yazımıyla
verilir:

```bash
pakize config set dictate_microphone "pulse:alsa_input.usb-Mikrofon"
```

Windows'ta varsayılan yoktur; `dshow` aygıtı adıyla ister:

```powershell
ffmpeg -list_devices true -f dshow -i dummy
pakize config set dictate_microphone "dshow:audio=Mikrofon (Realtek Audio)"
```

### Tanımayı iyileştirmek

İki ayar var, ikisi de config'te:

- `asr_context` — terimleri **cümle içinde anlatan** kısa bir paragraf. Model
  bunu arka plan bilgisi sayar: "seslendirmede edge-tts var" yazıyorsa, sen
  "ecdi tiitiies" dediğinde `edge-tts` yazar. Çıplak kelime listesi işe
  yaramaz.
- `[asr_replacements]` — bağlamla bile tutmayan kelimeler için düzeltme
  tablosu. Yalnız bütün kelime eşleşir; büyük-küçük harf ayrı sayılır, çünkü
  Türkçede `ılık` ile `ilik` ayrı kelimelerdir.

```toml
asr_context = "Pakize'yi uv ile kuruyorum; seslendirmede edge-tts ve Piper var."

[asr_replacements]
"Yuvı" = "uv"
"İpab" = "EPUB"
```

Tabloya dosyayı açmadan satır eklemek için:

```bash
pakize fix Yuvı uv            # yazar; varsa üzerine yazar
pakize fix --list             # tabloyu göster
pakize fix --remove Yuvı      # satırı sil
```

Ekli biçimler ayrı satır ister: `rümut` için yazılan düzeltme `rümutu`yu
yakalamaz, ona `pakize fix rümutu remote'u` gerekir.

### Bilinmesi gerekenler

Deşifre gerçek zamandan yavaştır ve uzun kayıtta süre orantıdan hızlı büyür;
dikte kısa parçalar hâlinde (bir iki cümle) en iyi çalışır. Uzun bir metni
bölüm bölüm dikte et.

Kısa bir cümle söyleyip hemen bitirdiysen sunucu hâlâ yükleniyor olabilir:
kayıt yine anında kapanır, "hazır" tonu yükleme bittikten sonra gelir.

Son diktenin kaydı `~/.cache/pakize/last-dictation.wav` olarak saklanır
(her dikte öncekinin üzerine yazar). Deşifre yanlış çıktıysa kaydı dinle ve
`pakize transcribe` ile yeniden dene: suçlu mikrofon mu model mi, oradan
anlaşılır.

Model kısa ya da belirsiz bir seste bazen sesi yazacağına `asr_context`
paragrafını olduğu gibi kopyalar. Pakize bunu yakalar ve aynı sesi bağlamsız
yeniden sorar; o seferlik terim yanlılığı olmaz, konuşma kaybolmaz.

Kendi sunucunu ayakta tutmak istersen `asr_server_url = "http://127.0.0.1:8099"`
yaz; Pakize o zaman sunucu açıp kapatmaz, olana bağlanır.

## Klavye kısayolu

Asıl kullanım şekli bu: metni kopyala, tuşa bas, dinle.

Panoyu okuma aracı platforma göre seçilir: macOS'ta `pbpaste`, Windows'ta
PowerShell'in `Get-Clipboard`'ı — ikisi de sistemle gelir. Linux'ta pencere
sistemine bağlıdır ve kurmak gerekir:

```bash
sudo apt install xclip      # X11 için (Wayland'de: wl-clipboard)
```

Beş kısayol yeterli. `pause` tek başına hem duraklatır hem sürdürür, o
yüzden "devam et" için ayrı bir tuşa gerek yok; `dictate` de aynı tuşla hem
başlar hem biter:

| Ad | Komut | Linux/Windows | macOS |
|----|-------|---------------|-------|
| `Pakize: panodakini oku` | `pakize speak --clipboard` | `Super+S` | `⌥⌘S` |
| `Pakize: duraklat` | `pakize pause` | `Super+Space` | `⌥⌘Space` |
| `Pakize: atla` | `pakize stop` | `Shift+Super+D` | `⇧⌥⌘D` |
| `Pakize: hepsini durdur` | `pakize stop --all` | `Ctrl+Shift+Super+D` | `⌃⇧⌥⌘D` |
| `Pakize: dikte` | `pakize dictate` | `Super+W` | `⌥⌘W` |

Okumalar sıraya girer: tuşa bastığın an kısa, yükselen bir "alındı" tonu
duyarsın; çalan bir şey varsa yeni metin onun bitmesini bekler, iki okuma asla
üst üste binmez. `stop` çalanı atlar ve sıradaki hemen başlar; `stop --all`
bekleyenlerle birlikte hepsini susturur. Aynı metin için tuşa ikinci kez
basarsan tek, pes bir ton duyarsın ve o basış yok sayılır.

### Linux (GNOME)

#### Arayüzden

**Ayarlar → Klavye → Klavye Kısayollarını Görüntüle ve Özelleştir → Özel
Kısayollar → +** — her satır için bir kısayol ekle.

#### Terminalden

Aynı işi yapar; Ayarlar ekranı da bu gsettings anahtarlarına yazar.

```bash
KOK=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
SEMA=org.gnome.settings-daemon.plugins.media-keys.custom-keybinding

kur() {  # kur <anahtar> <komut> <tuş> <ad>
  YOL="$KOK/$1/"
  gsettings set "$SEMA:$YOL" name "$4"
  gsettings set "$SEMA:$YOL" command "$2"
  gsettings set "$SEMA:$YOL" binding "$3"
  echo "'$YOL'"
}

YOLLAR=$(
  kur pakize-oku   "pakize speak --clipboard" '<Super>s'        'Pakize: panodakini oku'
  kur pakize-pause "pakize pause"             '<Super>space'    'Pakize: duraklat'
  kur pakize-stop  "pakize stop"              '<Shift><Super>d' 'Pakize: atla'
  kur pakize-stop-all "pakize stop --all"     '<Control><Shift><Super>d' 'Pakize: hepsini durdur'
  kur pakize-dikte "pakize dictate"           '<Super>w'        'Pakize: dikte'
)
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
  "[$(echo $YOLLAR | tr ' ' ',')]"
```

> Bu blok listeyi **baştan yazar**. Başka özel kısayolların varsa önce
> `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
> ile mevcut listeyi al ve yenileri onun üzerine ekle.

Kaldırmak için her yol için `gsettings reset-recursively "$SEMA:$YOL"` çalıştır
ve listeyi `"@as []"` yap.

#### Tam yol gerekir mi?

Genelde gerekmez: GNOME kısayolları oturumun `PATH`'ini miras alır ve Ubuntu'da
`~/.local/bin` orada bulunur. Kontrol et:

```bash
tr '\0' '\n' < /proc/$(pgrep -x gnome-shell | head -1)/environ | grep ^PATH=
```

Çıktıda `~/.local/bin` yoksa komutlarda tam yol kullan:
`/home/<kullanıcı>/.local/bin/pakize speak --clipboard`.

#### Tuş çakışması

`Super+Space` bazı kurulumlarda klavye düzeni değiştirmeye bağlıdır. Boş
olduğundan emin ol:

```bash
gsettings get org.gnome.desktop.wm.keybindings switch-input-source
```

`@as []` dönerse boştur.

### macOS

Sistemle gelen yol Automator'dır; ek yazılım gerekmez. Her komut için bir
Hızlı İşlem oluşturulur, sonra tuş atanır.

1. **Automator → Yeni Belge → Hızlı İşlem (Quick Action)**
2. Üstte: *İş akışı şunu alır:* **girdi yok**, *şurada:* **herhangi bir uygulama**
3. Soldan **Kabuk Betiği Çalıştır**'ı sürükle, içine yaz:

```bash
$HOME/.local/bin/pakize speak --clipboard
```

4. `Pakize: panodakini oku` adıyla kaydet; aynısını `pakize pause`,
   `pakize stop`, `pakize stop --all` ve `pakize dictate` için tekrarla.
5. **Sistem Ayarları → Klavye → Klavye Kısayolları → Hizmetler → Genel** —
   Hızlı İşlemlerin yanına tuşları yaz.

> **Tam yol şart.** Automator, giriş kabuğunun `PATH`'ini miras almaz; sadece
> `pakize` yazarsan "command not found" alırsın ve kısayol sessizce hiçbir şey
> yapmaz. Doğru yolu `which pakize` ile öğren.

Daha hafif bir yol istersen [`skhd`](https://github.com/koekeishiya/skhd) ile
tek dosyada birkaç satır yeter:

```
alt + cmd - s : $HOME/.local/bin/pakize speak --clipboard
alt + cmd - space : $HOME/.local/bin/pakize pause
shift + alt + cmd - d : $HOME/.local/bin/pakize stop
ctrl + shift + alt + cmd - d : $HOME/.local/bin/pakize stop --all
alt + cmd - w : $HOME/.local/bin/pakize dictate
```

### Windows

Sistemle gelen yol kısayol dosyasıdır (`.lnk`); ek yazılım gerekmez.

1. `Win+R` → `shell:programs` → açılan klasörde **sağ tık → Yeni → Kısayol**
2. Konum olarak yaz (kendi kullanıcı adınla):

```
%USERPROFILE%\.local\bin\pakize.exe speak --clipboard
```

3. `Pakize: panodakini oku` adıyla kaydet.
4. Kısayola **sağ tık → Özellikler → Kısayol tuşu** alanına tıkla ve tuş
   bileşimine bas (`Ctrl+Alt+S` gibi).
5. Aynısını `pause`, `stop`, `stop --all` ve `dictate` için tekrarla.

> Bu yöntemde her basışta kısa bir konsol penceresi yanıp söner. Rahatsız
> ediyorsa **Çalıştır** alanını *Simge durumunda* yap ya da
> [AutoHotkey](https://www.autohotkey.com/) kullan:

```autohotkey
#Requires AutoHotkey v2.0
#s::Run('pakize.exe speak --clipboard', , 'Hide')
#Space::Run('pakize.exe pause', , 'Hide')
+#d::Run('pakize.exe stop', , 'Hide')
^+#d::Run('pakize.exe stop --all', , 'Hide')
#w::Run('pakize.exe dictate', , 'Hide')
```

> `Win` tuşlu bileşimlerin çoğu Windows'ta rezervedir (`Win+S` arama açar).
> AutoHotkey bunları ezebilir, `.lnk` kısayolları ezemez — `.lnk` yolunda
> `Ctrl+Alt+<harf>` seç.

### Bilinmesi gerekenler

Kısayoldan tetiklediğinde ortada terminal olmaz; **hata mesajını göremezsin**.
Pano boşsa ya da ağ yoksa sessizce hiçbir şey olmaz. Ses gelmezse terminalde
`pakize speak -c` yazıp sebebi gör.

Ses hiç çalınamıyorsa (ffmpeg kurulu değil, ses aygıtı yok) hata masaüstü
bildirimiyle gelir: Linux'ta `notify-send` (Ubuntu'da hazır; yoksa
`sudo apt install libnotify-bin`), macOS'ta sistemin kendi bildirimi.
Windows'ta sistemle gelen bir bildirim aracı olmadığı için bu yedek yok.

`pause` ve `stop` yalnızca Pakize'nin başlattığı çalmayı yönetir; sistemdeki
başka `ffplay` süreçlerine dokunmaz. Duraklatılmışken `stop` çalışır. Terminalden
çalıştırdığında Ctrl+C de durdurur.

`--transcript` kısayola pek uygun değil: oturumu **çalışma dizinine** göre
seçer, kısayol ise ev dizininde çalışır. Bağlamak istersen komuta
`--session /yol/oturum.jsonl` ekle.

Bu komutlar `pakize replay` ile başlattığın çalmayı da yönetir.

Birden çok seslendirme başlattıysan (iki ayrı terminalden ya da tuşa art arda
basarak) sıraya girerler ve teker teker çalar. `stop` ve `pause` çalana
bakar; `stop --all` bekleyenleri de bitirir:

```
$ pakize stop --all
Durduruldu. (2 seslendirme)
```

`pakize book` ses çalmaz, yalnızca dosya üretir; bu yüzden arka planda bir
kitap üretilirken başka bir terminalden `pakize speak -c` çalıştırmak
çakışmaz.

## Yapılandırma

Ayarlar Linux ve macOS'ta `~/.config/pakize/config.toml`, Windows'ta
`%APPDATA%\pakize\config.toml` dosyasından okunur; `XDG_CONFIG_HOME` tanımlıysa
her üçünde de o kazanır. CLI bayrakları dosyayı ezer, dosya olmadan da çalışır.

Etkin yolu görmek için: `pakize config`.

Açıklamalı bir başlangıç dosyası oluşturmak için:

```bash
pakize config --init
```

Dosya, koddaki gerçek varsayılanlardan üretilir — ikinci bir doğruluk kaynağı
oluşmaz. Var olan dosyanın üzerine yazmaz.

Dosyayı elle düzenlemek istemeyen tek bir ayarı komutla yazabilir:

```bash
pakize config set voice de-AT-IngridNeural   # ana dili Almanca yap
pakize config set rate 1.2
pakize config set translate_to de            # metinleri önce Almancaya çevir
```

`set`, dosya yoksa açıklamalı varsayılanlarla oluşturur; varsa yalnızca ilgili
satırı değiştirir. Ses adı servis listesine karşı doğrulanır; motor adı
tanınanlarla sınırlıdır. Türkçe dışında bir ana dil kullanan, seçtiği dilin
metinlerini doğrudan o sesle dinler; `translate_to` ile birleştirirse başka
dildeki metinlerin çevirisini de aynı sesten dinler.

### Arayüz dili

CLI mesajları ve `--help` metinleri Türkçe ile İngilizce arasında kendiliğinden
seçilir: config'te `ui_language` doluysa o kazanır; boşsa sistem diline bakılır
(`LC_ALL` > `LC_MESSAGES` > `LANG`). Türkçe olmayan her sistem İngilizce görür.
Elle sabitlemek için:

```bash
pakize config set ui_language tr   # sistem dili ne olursa olsun Türkçe
pakize config set ui_language en
```

> Sistemi İngilizce kurulmuş Türkçe kullanıcılar (`LANG=en_US.UTF-8` yaygındır)
> Türkçe arayüz için bu ayarı bir kez yapmalı.

Hangi sesi seçeceğini bilmeyen için sihirbaz var:

```bash
pakize setup
```

Sihirbaz dilleri listeler, seçilen dilin seslerini numaralar ve istenen sesin
kısa bir örnek cümlesini çalarak dinletir; seçim config'e yazılır. Config
dosyası henüz yokken `speak`/`book` çalıştıran da tek satırlık bir ipucuyla
sihirbaza yönlendirilir. `pakize voices` her zaman üstte aktif sesin dilini
tam listeler — Almanca ses seçen, bir dahaki `voices` çağrısında üstte Almanca
sesleri görür.

```toml
voice = "tr-TR-EmelNeural"       # tr-TR-AhmetNeural de var
rate = 1.15                      # 1.0 = normal; ara değerler serbest (1.12 olur)
volume = 1.0
pitch_hz = 0                     # yalnızca edge motorunda
max_chunk_chars = 2500           # bir TTS isteğine sığdırılacak azami karakter
output_dir = "/tmp/pakize"       # çıktı yolu verilmediğinde seslerin biriktiği yer
                                 # (Windows'ta %TEMP%\pakize olarak üretilir)
stream = true                    # ilk parça hazır olunca çalmaya başla
normalize_decimals = true        # 1.15 → 1,15 (Türkçe ondalık okunuşu)

[policy]
# Her segment tipi için: "read" (oku), "announce" (anons et), "skip" (atla)
code_block      = "announce"
table           = "announce"
url             = "skip"
horizontal_rule = "skip"
file_path       = "read"
inline_code     = "read"
prose           = "read"
heading         = "read"
list_item       = "read"
quote           = "read"
```

### Politika ne işe yarar?

`announce` seçilen bir kod bloğu şöyle seslendirilir:

> Burada 12 satırlık bir Python kod bloğu var.

Böylece kodun kendisi okunmaz ama bağlam kaybolmaz. `skip` seçersen blok
tamamen atlanır. Satır içi `kod` ve bağlantılar cümlenin akışını bozmadan,
yerinde dönüştürülür.

Anons cümlesi **seçtiğin sesin diline** uyar; CLI mesajlarının diline değil.
`en-US-AndrewNeural` seçtiysen aynı yerde "There is a 12-line Python code block
here." duyarsın. Katalogda karşılığı olmayan diller (Almanca, Fransızca...)
İngilizce cümleye düşer — Türkçe bir cümlenin Almanca sesle okunmasından iyidir.

### Dosya yolları

`file_path` tipinde `read`, yolun tamamını değil **yalnızca dosya adını** okumak
demektir:

| Metinde | Okunan |
|---------|--------|
| `src/pakize/models.py` | "models.py" |
| `~/.config/pakize/config.toml` | "config.toml" |

"es-er-se bölü pakize bölü models nokta pe ye" dinlenebilir bir şey değil.
Yolun tamamen atlanmasını istersen `file_path = "skip"` yaz.

Yol sayılmak için en az bir `/` ve uzantılı bir son bileşen gerekir; bu sayede
`ve/veya` ya da `TR/EN` gibi ifadeler bozulmaz.

## Çevrimdışı yedek: Piper

`edge-tts` internete ve Microsoft'un resmî olmayan bir ucuna bağımlıdır. Piper
yerelde çalışır; ağ yoksa ya da servis bozulursa Pakize kendiliğinden ona düşer
ve bunu söyler:

```
Not: edge motoru çalışmadı, piper kullanıldı.
```

Kurulum iki parçadır — çalıştırılabilir ve ses modeli:

```bash
uv tool install piper-tts
```

Türkçe ses modelini [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/tr/tr_TR)
adresinden indir (`.onnx` ve yanındaki `.onnx.json` birlikte durmalı), sonra
config'e yaz:

```toml
fallback_engine = "piper"
piper_model = "/yol/tr_TR-dfki-medium.onnx"
piper_binary = "/yol/piper"        # boşsa PATH'te aranır
```

> Windows'ta yolları TOML'da ters bölüyle yazacaksan **çiftle**
> (`"C:\\sesler\\tr_TR-dfki-medium.onnx"`) ya da düz bölü kullan
> (`"C:/sesler/tr_TR-dfki-medium.onnx"`) — tek ters bölü TOML'da kaçış
> başlatır. `pakize config --init` ile üretilen dosya bunu kendisi halleder.

Yalnızca Piper kullanmak için `engine = "piper"` yaz ya da `--engine piper` ver.

Piper WAV üretir; hedef dosya `.mp3` ise birleştirme sırasında dönüştürülür.
Hız ayarı her iki motorda da aynı `rate` alanından gelir — Piper hızı süre
üzerinden ifade ettiği için değer içeride ters çevrilir.

İki motor da çalışmazsa **birincil motorun** hatası gösterilir; yedeğin
"kurulu değil" mesajı asıl sorunu gizlerdi.

## Çevrimdışı Türkçe motor: EMA Lightning

[EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) yerelde,
CPU'da çalışan Türkçe bir TTS modelidir: yalnızca Türkçe, tek ses, ağ gerekmez.
Türkçe doğallığı Piper'ın üstündedir; karşılığında her seslendirmede modelin
yüklenmesini bekler ve kurulumu daha büyüktür.

EMA torch ister; Pakize'nin kendisi ağır makine öğrenmesi bağımlılıkları
taşımaz. Bu yüzden EMA **ayrı bir Python ortamına** kurulur ve Pakize o ortamın
yorumlayıcısını alt süreç olarak çağırır. Üç platformda da aynı iki komut
(Windows'ta `~` yerine açık bir yol yaz; ema-lightning Python 3.11 ya da
üstü ister, bu yüzden sürüm komutta sabitlenir — uv gerekirse indirir):

```bash
uv venv --python 3.12 ~/.local/share/pakize-ema
uv pip install --python ~/.local/share/pakize-ema ema-lightning==1.0.1 torch --index https://download.pytorch.org/whl/cpu
```

Sonra config'e yorumlayıcının yolunu yaz:

```toml
engine = "ema"
ema_python = "~/.local/share/pakize-ema/bin/python"   # Windows: ~/.local/share/pakize-ema/Scripts/python.exe
```

Yalnızca yedek olarak kullanmak için `fallback_engine = "ema"`, tek seferlik
için `--engine ema`. Varsayılanlar değişmez: `edge` birincil, `piper` yedek.

Bedeli:

- Her seslendirmede yaklaşık **3 saniye açılış** (torch ve modelin yüklenmesi).
  Bir seslendirme boyunca tek bir işçi süreç çalışır, parçalar ona sırayla
  gider, iş bitince kapanır — başarıda, hatada ve Ctrl+C'de. Arkada sürekli
  duran bir şey yoktur.
- Kurulum yaklaşık **400 MB** (çoğu torch'un CPU sürümü; `--index` bayrağı
  PyPI'daki birkaç GB'lık CUDA sürümü yerine onu seçtirir).
- İlk kullanımda model dosyaları indirilir (yaklaşık 34 MB); sonra Hugging Face
  önbelleğinden gelir, ağ gerekmez. Kurulum eksikse ya da model yüklenemezse
  Pakize yedek motora geçer ve sebebini söyler.

Hız aynı `rate` alanından gelir ve olduğu gibi geçer (1.15 = %15 hızlı). EMA
0.25–4 aralığını kabul eder; dışındaki değer sessizce kırpılmaz, açık hata
verir. EMA Piper'dan 7–8 dB kısık çıktığı için her parça tepe 0.95'e normalize
edilir, sonra `volume` ile çarpılır; her parçanın sonuna kısa bir sönüm ve
0,85 sn sessizlik eklenir (edge'in kuyruğu kadar — akıcı modda her parçayı ayrı
bir ffplay çaldığı için daha kısa kuyrukta aygıt kapanırken cızırtı duyuluyordu).
EMA'ya giden metinde kesme işaretleri boşlukla değiştirilir: modelin metin
düzenleyicisi `EMA'nın` gibi harf harf okunan ifadelerde kesmeyi "kesme" diye
okuyor; bedeli `2026'da` gibi sayılarda ekin ayrı okunması. `pitch_hz` yalnızca
edge motorunda çalışır; EMA ve Piper bu ayarı yok sayar. Çıktı 48 kHz mono WAV'dır; hedef `.mp3` ise
birleştirmede dönüştürülür.

**Güvenlik notu.** `ema-lightning` paketi modeli `torch.load(weights_only=False)`
ile açar ve dosyaları sürüm sabitlemeden indirir; ilki pickle dosyasının
içindeki kodun çalışmasına izin verir. Pakize bunu yapmaz: model dosyaları
Hugging Face'ten **sabit bir revizyondan** indirilir, **sha256**'ları doğrulanır
ve her zaman **güvenli kipte** (`weights_only=True`) yüklenir. Bu yol paketin iç
fonksiyonlarına dayandığı için kurulu sürüm tam olarak 1.0.1 olmalı; başka
sürümde Pakize yüklemeyi reddeder ve kurulum komutunu söyler.

## Ondalık sayılar

Türkçe'de ondalık ayracı virgüldür. `1.15` yazımı TTS motoruna Türkçe
kurallarıyla gittiğinde yanlış okunur, bu yüzden `1,15`'e çevrilir.

Sürüm numaraları da aynı kalıba uyar: `Python 3.10` → "üç virgül on". İkisini
metne bakarak ayırmanın yolu yok. Sürüm numaraları senin için daha önemliyse
`normalize_decimals = false` yaz.

`1.2.3`, `192.168.1.1` ve `09.08.2026` gibi çok noktalı ifadelere dokunulmaz.

## Akıcı çalma

Varsayılan olarak ses, **ilk parça hazır olur olmaz** çalmaya başlar; kalan
parçalar arkadan üretilmeye devam eder. Uzun bir metinde ilk sese kadar
beklediğin süre, metnin tamamının değil yalnızca ilk parçanın süresidir.

Arşiv dosyası yine eksiksiz yazılır. Sesin baştan sona tek parça çalmasını
istersen `--no-stream` kullan veya config'te `stream = false` yaz.

## Hız hakkında

`edge-tts` hız ayarını yüzde olarak alır ve ara değer sınırı yoktur. Yani
`edge-tts.com` sitesindeki 1.25 / 1.5 gibi hazır kademelerle sınırlı değilsin;
`rate = 1.15` de `rate = 1.12` de çalışır. Varsayılan **1.15**.

## Mimari

```
metin
  → parsing/markdown.py   blok tespiti (kod, tablo, başlık, liste, alıntı)
  → parsing/policy.py     her tipe oku/anons/atla + satır içi normalizasyon
  → chunking.py           cümle sınırında, karakter limitine göre paketleme
  → engines/              TTS adaptörleri (edge, piper, ema; ema ayrı ortamda işçi süreç)
  → audio.py              ffmpeg ile birleştirme ve çalma
```

Ters yön, dikte:

```
ses
  → dictation.py          kayıt (ffmpeg), tonlar, iki basışın eşgüdümü
  → asr/server.py         deşifre sunucusunun ömrü: her iş için aç-kapat
  → asr/                  tanıma adaptörü (qwen) + düzeltme tablosu
  → sources/clipboard.py  metin panoya
```

Tüm arayüzler (CLI, pano kısayolu, transkript okuyucu, web paneli)
`pipeline.synthesize` fonksiyonunu çağırır; iş mantığı başka hiçbir yerde
tekrarlanmaz.

### Platform farkları nerede yaşıyor?

Bu boru hattının tamamı üç platformda aynı kodu çalıştırır. Sistemin kendisine
sorulması gereken her şey `platforms.py` içinde toplanmıştır — ayarların nereye
yazılacağı, geçici dizinin nerede olduğu, eksik bir aracın nasıl kurulacağı.
Başka hiçbir modül `sys.platform`'a bakmaz.

İki yerde daha davranış farkı var, ikisi de sarmalanmış durumda:

- **Süreç denetimi** (`runtime.py`) — çalan `ffplay`'i bulmak, duraklatmak ve
  kesmek için `psutil` kullanılır. Duraklatma POSIX'te `SIGSTOP`, Windows'ta
  `NtSuspendProcess`'tir; `psutil` ikisini tek çağrının arkasına saklar.
  `pakize stop` her platformda **önce sesi susturur, sonra süreci sonlandırır**:
  Windows'ta süreç sonlandırma sinyal işleyicisini çalıştırmaz, dolayısıyla ana
  süreç kendi `ffplay`'ini kesemeden ölür ve ses öksüz kalıp çalmayı sürdürürdü.
- **Pano** (`sources/clipboard.py`) — sistemin kendi aracı her zaman önce
  denenir, sonra pencere sistemine uyan araç.

## Testler

Testler hermetiktir: ağ erişimi, gerçek TTS çağrısı ve `ffmpeg` çalıştırması
yoktur; motor ve birleştirme yamalanır.

```bash
uv run pytest
```

## Lisans

Copyright (C) 2026 Mustafa Kahraman

[AGPL-3.0-or-later](LICENSE) — kullan, değiştir, dağıt; değiştirilmiş sürümü
dağıtan **veya bir ağ servisi olarak sunan**, kaynağını aynı lisansla açmak
zorundadır. 0.3.0 ve öncesi MIT ile yayımlanmıştı; o sürümler MIT kalır,
AGPL bu sürümden itibaren geçerlidir.

Bağımlılıkların lisansları ayrıdır ve kendi koşullarına tabidir:

| Bağımlılık | Lisans |
|------------|--------|
| `edge-tts` | LGPL-3.0 |
| `typer` | MIT |
| `psutil` | BSD-3-Clause |
| `tomli` | MIT |

Hepsi AGPL ile uyumludur; Pakize bunları paketin içine gömmez, ayrı paket
olarak kurulup içe aktarılırlar.
