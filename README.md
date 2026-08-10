# Pakize

Metni ses dosyasına çeviren yerel araç. Markdown'ı anlar: **kod bloklarını
okumaz**, yerlerine kısa bir anons koyar; tabloları, bağlantıları ve biçim
işaretlerini de politikaya göre eler.

- **Kaynaklar** — dosya, pano, stdin ya da Claude Code oturum kaydı
- **Kitap** — EPUB/PDF/MOBI'yi bölüm bölüm seslendirir, yarıda kalırsa devam eder
- **Çeviri** — seslendirmeden önce hedef dile çevirir
- **Motorlar** — edge-tts (çevrimiçi, kaliteli), ağ yoksa Piper'a düşer
- **Denetim** — klavye kısayoluyla oku, duraklat, durdur

## Kurulum

Gereksinimler: Python 3.10+, [uv](https://docs.astral.sh/uv/), `ffmpeg`.

```bash
sudo apt install ffmpeg
uv sync
```

Komutu her dizinden kullanabilmek için sisteme kur. `--editable` sayesinde
depoda yaptığın değişiklikler anında geçerli olur, yeniden kurmak gerekmez:

```bash
uv tool install --editable .
```

Bu, `~/.local/bin/pakize` çalıştırılabilirini oluşturur. Kaldırmak için:
`uv tool uninstall pakize`.

### Paketleme

Dağıtılabilir paketleri üretmek için:

```bash
uv build          # dist/ altına .whl ve .tar.gz yazar
```

Başka bir makineye kurmak:

```bash
uv tool install dist/pakize-0.1.0-py3-none-any.whl
```

Paket yalnızca Python bağımlılıklarını taşır. `ffmpeg` her kurulumda,
`calibre` kitap biçimleri için, `xclip` pano için, `piper` çevrimdışı yedek
için ayrıca gerekir.

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

Çıktı yolu verilmezse ses `/tmp/pakize/<tarih-saat>.mp3` altına yazılır ve hemen
çalmaya başlar. Sesler orada birikir; ileride lazım olan bir kaydı oradan
alabilirsin. `/tmp` yeniden başlatmada temizlendiği için kalıcı arşiv istiyorsan
`output_dir` ayarını değiştir.

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
pakize kitap kitap.epub    # bir kitabı bölüm bölüm seslendir
pakize duraklat            # çalmayı duraklat; duraklatılmışsa sürdür (aynı komut)
pakize dur                 # çalmakta olan seslendirmeyi durdur
pakize son                 # en son üretilen sesi yeniden çal
pakize son --list          # son üretilen sesleri tarihiyle listele
pakize son --list -n 30    # daha fazlasını göster
pakize voices              # Türkçe sesleri listele
pakize voices -l all       # tüm dilleri listele
pakize config              # etkin ayarları göster
pakize config --init       # açıklamalı config dosyası oluştur
```

## Çeviri

Metni seslendirmeden önce çevirir. İngilizce bir kitabı Türkçe dinlemek için:

```bash
pakize speak makale.md --translate tr    # veya -T tr
pakize kitap kitap.epub --translate tr
pakize speak -t -T en                    # son cevabı İngilizce dinle
```

Kaynak dil kendiliğinden tespit edilir; zaten hedef dildeyse metne dokunulmaz.
Kalıcı hâle getirmek için config'e `translate_to = "tr"` yaz.

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
pakize kitap kitap.epub                  # bölümler /tmp/pakize/kitap/ altına
pakize kitap kitap.pdf -o ~/Müzik/kitap  # başka bir dizine
pakize kitap kitap.md --dry-run          # bölüm listesini gör, ses üretme
pakize kitap kitap.epub -l 1             # yalnızca '#' başlıkları bölüm sayılsın
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
sudo apt install calibre
```

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

## Klavye kısayolu (GNOME)

Asıl kullanım şekli bu: metni kopyala, tuşa bas, dinle.

Pano okuma X11'de `xclip`/`xsel`, Wayland'de `wl-paste` ile yapılır; oturum
tipine uygun olan kendiliğinden seçilir.

```bash
sudo apt install xclip      # X11 için
```

Üç kısayol yeterli. `duraklat` tek başına hem duraklatır hem sürdürür, o
yüzden "devam et" için ayrı bir tuşa gerek yok:

| Ad | Komut | Kısayol örneği |
|----|-------|----------------|
| `Pakize: panodakini oku` | `pakize speak --clipboard` | `Super+S` |
| `Pakize: duraklat` | `pakize duraklat` | `Super+Space` |
| `Pakize: durdur` | `pakize dur` | `Shift+Super+D` |

### Arayüzden

**Ayarlar → Klavye → Klavye Kısayollarını Görüntüle ve Özelleştir → Özel
Kısayollar → +** — her satır için bir kısayol ekle.

### Terminalden

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
  kur pakize-oku      "pakize speak --clipboard" '<Super>s'        'Pakize: panodakini oku'
  kur pakize-duraklat "pakize duraklat"          '<Super>space'    'Pakize: duraklat'
  kur pakize-dur      "pakize dur"               '<Shift><Super>d' 'Pakize: durdur'
)
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
  "[$(echo $YOLLAR | tr ' ' ',')]"
```

> Bu blok listeyi **baştan yazar**. Başka özel kısayolların varsa önce
> `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
> ile mevcut listeyi al ve yenileri onun üzerine ekle.

Kaldırmak için her yol için `gsettings reset-recursively "$SEMA:$YOL"` çalıştır
ve listeyi `"@as []"` yap.

### Tam yol gerekir mi?

Genelde gerekmez: GNOME kısayolları oturumun `PATH`'ini miras alır ve Ubuntu'da
`~/.local/bin` orada bulunur. Kontrol et:

```bash
tr '\0' '\n' < /proc/$(pgrep -x gnome-shell | head -1)/environ | grep ^PATH=
```

Çıktıda `~/.local/bin` yoksa komutlarda tam yol kullan:
`/home/<kullanıcı>/.local/bin/pakize speak --clipboard`.

### Tuş çakışması

`Super+Space` bazı kurulumlarda klavye düzeni değiştirmeye bağlıdır. Boş
olduğundan emin ol:

```bash
gsettings get org.gnome.desktop.wm.keybindings switch-input-source
```

`@as []` dönerse boştur.

### Bilinmesi gerekenler

Kısayoldan tetiklediğinde ortada terminal olmaz; **hata mesajını göremezsin**.
Pano boşsa ya da ağ yoksa sessizce hiçbir şey olmaz. Ses gelmezse terminalde
`pakize speak -c` yazıp sebebi gör.

`duraklat` ve `dur` yalnızca Pakize'nin başlattığı çalmayı yönetir; sistemdeki
başka `ffplay` süreçlerine dokunmaz. Duraklatılmışken `dur` çalışır. Terminalden
çalıştırdığında Ctrl+C de durdurur.

`--transcript` kısayola pek uygun değil: oturumu **çalışma dizinine** göre
seçer, kısayol ise ev dizininde çalışır. Bağlamak istersen komuta
`--session /yol/oturum.jsonl` ekle.

Bu komutlar `pakize son` ile başlattığın çalmayı da yönetir.

Aynı anda birden çok seslendirme çalıyorsa (iki ayrı terminalden başlattıysan)
ikisi de yönetilir — `dur` hepsini durdurur, `duraklat` hepsini duraklatır:

```
$ pakize dur
Durduruldu. (2 seslendirme)
```

`pakize kitap` ses çalmaz, yalnızca dosya üretir; bu yüzden arka planda bir
kitap üretilirken başka bir terminalden `pakize speak -c` çalıştırmak
çakışmaz.

### Akıcı çalma

Varsayılan olarak ses, **ilk parça hazır olur olmaz** çalmaya başlar; kalan
parçalar arkadan üretilmeye devam eder. Uzun bir metinde ilk sese kadar
beklediğin süre, metnin tamamının değil yalnızca ilk parçanın süresidir.

Arşiv dosyası yine eksiksiz yazılır. Sesin baştan sona tek parça çalmasını
istersen `--no-stream` kullan veya config'te `stream = false` yaz.

## Yapılandırma

Ayarlar `~/.config/pakize/config.toml` dosyasından okunur; CLI bayrakları bu
dosyayı ezer. Dosya olmadan da çalışır.

Açıklamalı bir başlangıç dosyası oluşturmak için:

```bash
pakize config --init
```

Dosya, koddaki gerçek varsayılanlardan üretilir — ikinci bir doğruluk kaynağı
oluşmaz. Var olan dosyanın üzerine yazmaz.

```toml
voice = "tr-TR-EmelNeural"       # tr-TR-AhmetNeural de var
rate = 1.15                      # 1.0 = normal; ara değerler serbest (1.12 olur)
volume = 1.0
pitch_hz = 0
max_chunk_chars = 2500           # bir TTS isteğine sığdırılacak azami karakter
output_dir = "/tmp/pakize"       # çıktı yolu verilmediğinde seslerin biriktiği yer
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

## Testler

Testler hermetiktir: ağ erişimi, gerçek TTS çağrısı ve `ffmpeg` çalıştırması
yoktur; motor ve birleştirme yamalanır.

```bash
uv run pytest
```
