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

# Panodan (X11)
xclip -o -selection clipboard | pakize speak

# Borudan
echo "Okunacak metin" | pakize speak

# Ses üretmeden neyin okunacağını gör
pakize speak notlar.md --dry-run

# Belirli bir dosyaya yaz, otomatik çalma
pakize speak notlar.md -o cikti.mp3 --no-play
```

> Sisteme kurmadıysan komutların başına `uv run` ekle ve proje dizininden çalıştır.

Çıktı yolu verilmezse ses `~/.local/share/pakize/<tarih-saat>.mp3` altına yazılır
ve hemen çalmaya başlar.

### Bayraklar

| Bayrak | Açıklama |
|--------|----------|
| `-o, --output` | Üretilecek ses dosyasının yolu |
| `-v, --voice` | TTS sesi (örn. `tr-TR-AhmetNeural`) |
| `-r, --rate` | Konuşma hızı çarpanı (örn. `1.15`) |
| `-e, --engine` | Kullanılacak motor |
| `--no-play` | Ses hazır olunca otomatik çalma |
| `--dry-run` | Ses üretmeden okunacak metni göster |

### Diğer komutlar

```bash
pakize voices              # Türkçe sesleri listele
pakize voices -l all       # tüm dilleri listele
pakize config              # etkin ayarları göster
```

## Yapılandırma

Ayarlar `~/.config/pakize/config.toml` dosyasından okunur; CLI bayrakları bu
dosyayı ezer. Dosya olmadan da çalışır.

```toml
voice = "tr-TR-EmelNeural"       # tr-TR-AhmetNeural de var
rate = 1.15                      # 1.0 = normal; ara değerler serbest (1.12 olur)
volume = 1.0
pitch_hz = 0
max_chunk_chars = 2500           # bir TTS isteğine sığdırılacak azami karakter

[policy]
# Her segment tipi için: "read" (oku), "announce" (anons et), "skip" (atla)
code_block      = "announce"
table           = "announce"
url             = "skip"
horizontal_rule = "skip"
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
