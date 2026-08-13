[English](README.en.md) · **Türkçe**

# Pakize

Metni ses dosyasına çeviren yerel araç. Markdown'ı anlar: **kod bloklarını
okumaz**, yerlerine kısa bir anons koyar; tabloları, bağlantıları ve biçim
işaretlerini de politikaya göre eler.

- **Kaynaklar** — dosya, pano, stdin ya da Claude Code oturum kaydı
- **Kitap** — EPUB/PDF/MOBI'yi bölüm bölüm seslendirir, yarıda kalırsa devam eder
- **Çeviri** — seslendirmeden önce hedef dile çevirir
- **Motorlar** — edge-tts (çevrimiçi, kaliteli), ağ yoksa Piper'a düşer
- **Denetim** — klavye kısayoluyla oku, duraklat, durdur
- **Platformlar** — Linux, macOS ve Windows

> **Resmî olmayan servisler.** Pakize sesi `edge-tts` üzerinden Microsoft'un
> Edge "Read Aloud" ucundan, çeviriyi Google'ın ücretsiz çeviri ucundan alır.
> İkisi de **belgelenmiş, resmî olarak desteklenen API'ler değildir**: kota
> belirsizdir, herhangi bir zaman değişebilir ya da kapanabilir ve ilgili
> şirketlerin kullanım şartları üçüncü taraf kullanımını öngörmez. Kişisel
> kullanım için düşünülmüştür; ticari ya da yoğun kullanım öncesinde bunu
> değerlendirmek sana düşer. Ağ gerektirmeyen tam yerel bir alternatif için
> [Piper](#çevrimdışı-yedek-piper) bölümüne bak.

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

**Hazır paket (`.whl` dosyası) aldıysan** — dosyanın bulunduğu dizinde:

```bash
uv tool install pakize-0.3.0-py3-none-any.whl
```

**Depodan kuruyorsan** — proje dizininde:

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

**`git pull` tek başına yetmez.** `--editable` kurulumda kod anında güncellenir
ama bağımlılık listesi değiştiyse araç ortamı eski kalır ve şuna benzer bir hata
alırsın:

```
ModuleNotFoundError: No module named 'psutil'
```

Yeniden kurmak yeterli — `--force`, var olan kurulumun üzerine yazar:

```bash
uv tool install --editable . --force
```

Hazır paketten kurduysan yeni `.whl` dosyasıyla aynı komutu çalıştır:

```bash
uv tool install pakize-0.3.0-py3-none-any.whl --force
```

### İsteğe bağlı araçlar

Yukarıdakiler temel kullanım için yeter. Şu özellikleri kullanacaksan
karşılarındaki aracı da kur:

| Araç | Ne için | Linux | macOS | Windows |
|------|---------|-------|-------|---------|
| `calibre` | EPUB/PDF/MOBI seslendirme | `sudo apt install calibre` | `brew install --cask calibre` | `winget install calibre.calibre` |
| pano aracı | `--clipboard` | `sudo apt install xclip` | sistemle gelir (`pbpaste`) | sistemle gelir (PowerShell) |
| `piper` | çevrimdışı yedek motor | `uv tool install piper-tts` | aynı | aynı |

Pakize eksik bir araçla karşılaştığında **bulunduğun platformun** kurulum
komutunu söyler; hata mesajındaki komutu olduğu gibi çalıştırabilirsin.

### Paketleme

Başkasına göndermek üzere dağıtılabilir paket üretmek için:

```bash
uv build          # dist/ altına .whl ve .tar.gz yazar
```

Üretilen `.whl` dosyasını gönderdiğin kişi yukarıdaki 1-2-3. adımları
uygulayarak kurar. Paket yalnızca Python bağımlılıklarını taşır; `ffmpeg` ve
isteğe bağlı araçlar her makinede ayrıca gerekir.

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
pakize pause                  # çalmayı duraklat; duraklatılmışsa sürdür (aynı komut)
pakize stop                   # çalmakta olan seslendirmeyi durdur
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

## Klavye kısayolu

Asıl kullanım şekli bu: metni kopyala, tuşa bas, dinle.

Panoyu okuma aracı platforma göre seçilir: macOS'ta `pbpaste`, Windows'ta
PowerShell'in `Get-Clipboard`'ı — ikisi de sistemle gelir. Linux'ta pencere
sistemine bağlıdır ve kurmak gerekir:

```bash
sudo apt install xclip      # X11 için (Wayland'de: wl-clipboard)
```

Üç kısayol yeterli. `pause` tek başına hem duraklatır hem sürdürür, o
yüzden "devam et" için ayrı bir tuşa gerek yok:

| Ad | Komut | Linux/Windows | macOS |
|----|-------|---------------|-------|
| `Pakize: panodakini oku` | `pakize speak --clipboard` | `Super+S` | `⌥⌘S` |
| `Pakize: duraklat` | `pakize pause` | `Super+Space` | `⌥⌘Space` |
| `Pakize: durdur` | `pakize stop` | `Shift+Super+D` | `⇧⌥⌘D` |

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
  kur pakize-stop  "pakize stop"              '<Shift><Super>d' 'Pakize: durdur'
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

Sistemle gelen yol Automator'dır; ek yazılım gerekmez. Üç komutun her biri için
bir Hızlı İşlem oluşturulur, sonra tuş atanır.

1. **Automator → Yeni Belge → Hızlı İşlem (Quick Action)**
2. Üstte: *İş akışı şunu alır:* **girdi yok**, *şurada:* **herhangi bir uygulama**
3. Soldan **Kabuk Betiği Çalıştır**'ı sürükle, içine yaz:

```bash
$HOME/.local/bin/pakize speak --clipboard
```

4. `Pakize: panodakini oku` adıyla kaydet; aynısını `pakize pause` ve
   `pakize stop` için tekrarla.
5. **Sistem Ayarları → Klavye → Klavye Kısayolları → Hizmetler → Genel** —
   üç Hızlı İşlemin yanına tuşları yaz.

> **Tam yol şart.** Automator, giriş kabuğunun `PATH`'ini miras almaz; sadece
> `pakize` yazarsan "command not found" alırsın ve kısayol sessizce hiçbir şey
> yapmaz. Doğru yolu `which pakize` ile öğren.

Daha hafif bir yol istersen [`skhd`](https://github.com/koekeishiya/skhd) ile
tek dosyada üç satır yeter:

```
alt + cmd - s : $HOME/.local/bin/pakize speak --clipboard
alt + cmd - space : $HOME/.local/bin/pakize pause
shift + alt + cmd - d : $HOME/.local/bin/pakize stop
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
5. Aynısını `pause` ve `stop` için tekrarla.

> Bu yöntemde her basışta kısa bir konsol penceresi yanıp söner. Rahatsız
> ediyorsa **Çalıştır** alanını *Simge durumunda* yap ya da
> [AutoHotkey](https://www.autohotkey.com/) kullan:

```autohotkey
#Requires AutoHotkey v2.0
#s::Run('pakize.exe speak --clipboard', , 'Hide')
#Space::Run('pakize.exe pause', , 'Hide')
+#d::Run('pakize.exe stop', , 'Hide')
```

> `Win` tuşlu bileşimlerin çoğu Windows'ta rezervedir (`Win+S` arama açar).
> AutoHotkey bunları ezebilir, `.lnk` kısayolları ezemez — `.lnk` yolunda
> `Ctrl+Alt+<harf>` seç.

### Bilinmesi gerekenler

Kısayoldan tetiklediğinde ortada terminal olmaz; **hata mesajını göremezsin**.
Pano boşsa ya da ağ yoksa sessizce hiçbir şey olmaz. Ses gelmezse terminalde
`pakize speak -c` yazıp sebebi gör.

`pause` ve `stop` yalnızca Pakize'nin başlattığı çalmayı yönetir; sistemdeki
başka `ffplay` süreçlerine dokunmaz. Duraklatılmışken `stop` çalışır. Terminalden
çalıştırdığında Ctrl+C de durdurur.

`--transcript` kısayola pek uygun değil: oturumu **çalışma dizinine** göre
seçer, kısayol ise ev dizininde çalışır. Bağlamak istersen komuta
`--session /yol/oturum.jsonl` ekle.

Bu komutlar `pakize replay` ile başlattığın çalmayı da yönetir.

Aynı anda birden çok seslendirme çalıyorsa (iki ayrı terminalden başlattıysan)
ikisi de yönetilir — `stop` hepsini durdurur, `pause` hepsini duraklatır:

```
$ pakize stop
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
pitch_hz = 0
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
  → engines/              TTS adaptörü (edge; yedek motor takılabilir)
  → audio.py              ffmpeg ile birleştirme ve çalma
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
