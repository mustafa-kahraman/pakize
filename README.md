# Pakize

Metni ses dosyasına çeviren yerel araç. Markdown'ı anlar: **kod bloklarını
okumaz**, yerlerine kısa bir anons koyar; tabloları, bağlantıları ve biçim
işaretlerini de politikaya göre eler.

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

## Kullanım

```bash
# Dosyadan
pakize speak notlar.md

# Panodan
pakize speak --clipboard

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
| `-o, --output` | Üretilecek ses dosyasının yolu |
| `-v, --voice` | TTS sesi (örn. `tr-TR-AhmetNeural`) |
| `-r, --rate` | Konuşma hızı çarpanı (örn. `1.15`) |
| `-e, --engine` | Kullanılacak motor |
| `--no-play` | Ses hazır olunca otomatik çalma |
| `--no-stream` | Parçaları beklet, hepsi bitince tek seferde çal |
| `--dry-run` | Ses üretmeden okunacak metni göster |

### Diğer komutlar

```bash
pakize dur                 # çalmakta olan seslendirmeyi durdur
pakize son                 # en son üretilen sesi yeniden çal
pakize son --list          # son üretilen sesleri tarihiyle listele
pakize son --list -n 30    # daha fazlasını göster
pakize voices              # Türkçe sesleri listele
pakize voices -l all       # tüm dilleri listele
pakize config              # etkin ayarları göster
pakize config --init       # açıklamalı config dosyası oluştur
```

## Klavye kısayolu (GNOME)

Asıl kullanım şekli bu: metni kopyala, tuşa bas, dinle.

Pano okuma X11'de `xclip`/`xsel`, Wayland'de `wl-paste` ile yapılır; oturum
tipine uygun olan kendiliğinden seçilir.

```bash
sudo apt install xclip      # X11 için
```

### Arayüzden

**Ayarlar → Klavye → Klavye Kısayollarını Görüntüle ve Özelleştir → Özel
Kısayollar → +**

| Alan | Değer |
|------|-------|
| Ad | `Pakize: panodakini oku` |
| Komut | `/home/mustafa/.local/bin/pakize speak --clipboard` |
| Kısayol | tercihin (örn. `Super+Alt+P`) |

> Komutta **tam yol** kullan. Kısayollar `~/.local/bin` dizinini `PATH`'te
> göremeyebilir.

### Terminalden

Aşağıdaki blok mevcut özel kısayolları silmeden yenisini ekler:

```bash
ANAHTAR=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pakize/
YOL=org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$ANAHTAR

MEVCUT=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
case "$MEVCUT" in
  *"$ANAHTAR"*) ;;                                    # zaten ekli
  "@as []"|"[]") YENI="['$ANAHTAR']" ;;
  *) YENI="${MEVCUT%]}, '$ANAHTAR']" ;;
esac
[ -n "$YENI" ] && gsettings set org.gnome.settings-daemon.plugins.media-keys \
  custom-keybindings "$YENI"

gsettings set "$YOL" name 'Pakize: panodakini oku'
gsettings set "$YOL" command "$HOME/.local/bin/pakize speak --clipboard"
gsettings set "$YOL" binding '<Super><Alt>p'
```

Kaldırmak için `gsettings reset-recursively "$YOL"` çalıştır ve kısayolu
listeden çıkar.

### Durdurma kısayolu

Kısayoldan tetiklediğinde ortada terminal olmaz; Ctrl+C ile durduramazsın. Bu
yüzden ikinci bir kısayol daha bağla:

| Alan | Değer |
|------|-------|
| Ad | `Pakize: durdur` |
| Komut | `/home/mustafa/.local/bin/pakize dur` |
| Kısayol | tercihin (örn. `Super+Alt+D`) |

`pakize dur` yalnızca Pakize'nin başlattığı çalmayı sonlandırır; sistemdeki
başka `ffplay` süreçlerine dokunmaz. Çalan bir şey yoksa "Çalan bir seslendirme
yok." der. Terminalden çalıştırdığında Ctrl+C de aynı işi görür.

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
