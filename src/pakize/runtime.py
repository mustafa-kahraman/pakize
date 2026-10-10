"""Çalmakta olan seslendirmenin süreç kaydı, okuma kuyruğu ve denetimi.

`pakize stop` ve `pakize pause`, çalmayı başlatan sürece ulaşabilmek için bu
kaydı okur. Kayıt geçici dizin altında tutulur; oturum kapanınca işletim
sistemi temizler.

Kayıt aynı zamanda bir kuyruktur: her çalacak süreç sıraya girer ve kendinden
eski yaşayan kayıt kalmayana kadar bekler; böylece iki Pakize asla üst üste
çalmaz. Sıra, kayda yazılan zaman damgasıyla belirlenir (eşitlikte küçük
süreç numarası önde); dosya değişiklik zamanı dosya sistemine göre kaba
olabildiği için kullanılmaz. Sıranın başı çalmaya ancak tek bir kilit
dosyasını (`O_EXCL`) oluşturabilince başlar: kayıt, damgası alındıktan sonra
görünür olduğu için sıra tek başına üst üste çalmayı engelleyemiyordu. POSIX
kilidi kullanılmaz; `O_EXCL` Windows'ta da çalışır.

Kayıt yalnızca bir ipucudur: süreç kimlikleri yeniden kullanılabildiği için
okurken sürecin gerçekten Pakize olduğu doğrulanır.

Süreç ağacına doğrudan işletim sistemi arayüzleriyle değil `psutil` üzerinden
bakarız: Linux'ta `/proc`, macOS'ta `sysctl`, Windows'ta `NtQuerySystemInfo`
gerekir ve duraklatmanın Windows karşılığı sinyal değil `NtSuspendProcess`'tir.
Tek kod yolu ancak bu soyutlamayla mümkün.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from .platforms import temp_root

STATE_NAME = "pakize-playing"
"""Çalan ve sırada bekleyen seslendirmelerin kaydı; `stop` ve `pause` buna bakar."""

DICTATION_STATE_NAME = "pakize-dictating"
"""Süren diktelerin kaydı; ikinci `pakize dictate` çağrısı buna bakar."""

PLAYER_COMM = "ffplay"
"""Çalmayı yürüten sürecin adı (Windows'ta `ffplay.exe` olarak görünür)."""

QUEUE_POLL_SECONDS = 0.2
"""Sıranın gelip gelmediğine bakma aralığı; sıradaki en çok bu kadar geç başlar."""

LOCK_NAME = "playing.lock"
"""Çalma kilidi dosyası; içinde kilidi tutan sürecin numarası yazar."""


@dataclass(frozen=True)
class Entry:
    """Kayıttaki tek bir süreç."""

    pid: int
    registered_ns: int
    """Kayda giriş anı (`time.time_ns()`); sıra buna göre kurulur."""
    text_hash: str | None
    """Okunan metnin sha256'sı; metinsiz çalmalarda (kitap, tekrar, uyarı) None."""


def state_dir(name: str = STATE_NAME) -> Path:
    """Süreç kayıtlarının tutulduğu dizin.

    Her çalan süreç için ayrı bir dosya tutulur. Tek dosya kullanmak, aynı
    anda iki Pakize çaldığında birinin kaydını ezip o sürecin durdurulamaz
    hâle gelmesine yol açıyordu.

    Her kayıt türünün (çalma, dikte) kendi dizini vardır: `pakize stop`
    süren bir dikteyi, ikinci `pakize dictate` de çalan bir sesi görmez.
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else temp_root()
    return root / name


def register(pid: int, name: str = STATE_NAME, text: str | None = None) -> None:
    """Süreci kaydeder ve sıranın sonuna ekler.

    Metin verilirse yalnızca özeti yazılır; tekrar tespiti ona bakar, metnin
    kendisi kayda girmez. Dosya önce geçici ada yazılıp taşınır: sırayı okuyan
    bir süreç yarım dosyayla karşılaşmasın.
    """
    directory = state_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "registered_ns": time.time_ns(),
        "text_hash": _text_hash(text) if text is not None else None,
    }
    target = directory / str(pid)
    partial = directory / f"{pid}.partial"
    partial.write_text(json.dumps(record), encoding="utf-8")
    os.replace(partial, target)


def clear(pid: int, name: str = STATE_NAME) -> None:
    """Bir sürecin kaydını siler; diğerlerine dokunmaz."""
    _remove_quietly(state_dir(name) / str(pid))


def entries(name: str = STATE_NAME) -> list[Entry]:
    """Kayıtlı ve hâlâ yaşayan Pakize süreçleri; sıra düzeninde, en eski önde.

    En öndeki sıradaki ilk adaydır; çalan, kilidi tutandır (bkz. `lock_holder`).
    Bayat kayıtlar sessizce temizlenir.
    """
    directory = state_dir(name)
    if not directory.is_dir():
        return []

    alive: list[Entry] = []
    for path in directory.iterdir():
        if not path.name.isdigit():
            continue
        pid = int(path.name)
        if not _is_pakize(pid):
            _remove_quietly(path)
            continue
        alive.append(_read_entry(pid, path))

    return sorted(alive, key=lambda entry: (entry.registered_ns, entry.pid))


def running_pids(name: str = STATE_NAME) -> list[int]:
    """Kayıtlı ve hâlâ yaşayan Pakize süreçleri; sıra düzeninde, en eski önde."""
    return [entry.pid for entry in entries(name)]


def running_pid() -> int | None:
    """Sıranın başındaki süreç; yoksa None."""
    pids = running_pids()
    return pids[0] if pids else None


def playing_pid(name: str = STATE_NAME) -> int | None:
    """Şu an çalan süreç: kilidi tutan; kilit yoksa sıranın başı; kimse yoksa None.

    Kilit sahibi kayıtta görünmüyorsa (bayat kilit) sıranın başına düşülür.
    """
    pids = running_pids(name)
    holder = lock_holder(name)
    if holder in pids:
        return holder
    return pids[0] if pids else None


def wait_for_turn(pid: int, name: str = STATE_NAME) -> None:
    """Sıra gelene kadar bekler: süreç hem sıranın başı olmalı hem kilidi almalı.

    Sıra tek başına yetmez: kayıt, zaman damgası alındıktan sonra görünür olur;
    arada kendini baş sanan daha yeni bir kayıt çalmaya başlamış olabilir.
    Kilit bu pencereyi kapatır — çalan kilidi bırakmadan ikincisi başlamaz.

    Kendi kaydı silinmişse de döner: `pakize stop` süreci zaten
    sonlandırıyordur, burada takılı kalmanın anlamı yok.
    """
    while True:
        pids = running_pids(name)
        if pid not in pids:
            return
        if pids[0] == pid and acquire_lock(pid, name):
            return
        time.sleep(QUEUE_POLL_SECONDS)


def earlier_duplicate(pid: int, name: str = STATE_NAME) -> bool:
    """Sırada bu süreçten önde ya da kilidi tutan kayıtlardan biri aynı metni taşıyor mu?

    Önce kaydolup sonra bakmak yarışı belirli kılar: aynı anda giren iki
    süreçten sıralamada arkada kalan tekrar sayılır, öndeki kalır. Kilidi
    tutan da sayılır: daha yeni bir kayıt görünürlük penceresinde çalmaya
    başlamışsa, sırada ondan önde görünen aynı metin de tekrardır. Metinsiz
    kayıtlar hiçbir şeyle eşleşmez.
    """
    queue = entries(name)
    own = next((entry for entry in queue if entry.pid == pid), None)
    if own is None or own.text_hash is None:
        return False
    holder = lock_holder(name)
    ahead = [
        entry
        for entry in queue
        if entry.pid != pid and (queue.index(entry) < queue.index(own) or entry.pid == holder)
    ]
    return any(entry.text_hash == own.text_hash for entry in ahead)


def acquire_lock(pid: int, name: str = STATE_NAME) -> bool:
    """Çalma kilidini almayı dener; alındıysa True.

    Kilit, `O_EXCL` ile oluşturulan tek bir dosyadır: aynı anda yalnız bir
    süreç oluşturabilir, Windows'ta da çalışır. Sahibi ölmüş bir kilit bayat
    sayılıp kaldırılır ve hemen yeniden denenir.
    """
    path = _lock_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not _remove_stale_lock(path):
                return False
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(pid))
        return True
    return False


def release_lock(pid: int, name: str = STATE_NAME) -> None:
    """Kilidi bırakır; yalnız kendi kilidini siler, başkasınınkine dokunmaz."""
    path = _lock_path(name)
    if _read_lock(path) == pid:
        _remove_quietly(path)


def lock_holder(name: str = STATE_NAME) -> int | None:
    """Kilidi tutan süreç; kilit yoksa ya da henüz yazılmamışsa None."""
    return _read_lock(_lock_path(name))


def _lock_path(name: str) -> Path:
    return state_dir(name) / LOCK_NAME


def _read_lock(path: Path) -> int | None:
    """Kilit dosyasındaki süreç numarası; dosya yoksa ya da henüz boşsa None."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _remove_stale_lock(path: Path) -> bool:
    """Sahibi ölmüş kilidi kaldırır; kaldırdıysa True.

    Boş kilit bayat değildir: sahibi dosyayı açmış, numarasını henüz
    yazmamıştır. Silmeden hemen önce yeniden okunur; arada başka bir süreç
    bayat kilidi kaldırıp kendi kilidini koymuşsa o taze kilit silinmez.
    """
    holder = _read_lock(path)
    if holder is None or _is_pakize(holder):
        return False
    if _read_lock(path) != holder:
        return False
    _remove_quietly(path)
    return True


def _remove_quietly(path: Path) -> None:
    """Dosyayı siler; yoksa ya da silinemiyorsa sessiz kalır.

    Windows'ta başka bir sürecin o an okuduğu dosya silinemez
    (`PermissionError`). Dosya yerinde kalır; sahibi öldüğü için sonraki
    okumada bayat sayılıp yok sayılır. Çıkış yolunu bu yüzden kırmayız.
    """
    try:
        path.unlink()
    except (FileNotFoundError, PermissionError):
        return


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_entry(pid: int, path: Path) -> Entry:
    """Kayıt dosyasını çözer.

    Önceki sürümler dosyaya yalnızca süreç numarasını yazıyordu; güncelleme
    sırasında yaşayan böyle bir kayıt çalan sayılır ve sıranın başına alınır.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return Entry(
            pid=pid,
            registered_ns=int(record["registered_ns"]),
            text_hash=record.get("text_hash"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return Entry(pid=pid, registered_ns=0, text_hash=None)


def pause(pid: int) -> bool:
    """Sürecin çalma alt süreçlerini duraklatır.

    Duraklatılacak bir şey yoksa False döner.
    """
    return _apply(pid, "suspend")


def resume(pid: int) -> bool:
    """Duraklatılmış çalmayı sürdürür."""
    return _apply(pid, "resume")


def is_paused(pid: int) -> bool:
    """Çalma şu an duraklatılmış mı?"""
    players = _players(pid)
    return bool(players) and all(_is_suspended(player) for player in players)


def stop(pid: int) -> bool:
    """Çalmayı keser ve süreci sonlandırır.

    Önce çalan sesler susturulur, sonra ana süreç sonlandırılır. Sıra kasıtlı:
    Windows'ta süreç sonlandırma sinyal işleyicisini çalıştırmaz, dolayısıyla
    ana süreç kendi ffplay'ini kesemeden ölür ve ses öksüz kalıp çalmayı
    sürdürürdü.

    Süreç zaten ölmüşse False döner; çağıran bunu hata saymamalıdır.
    """
    _terminate_players(pid)

    try:
        psutil.Process(pid).terminate()
    except psutil.NoSuchProcess:
        clear(pid)
        return False
    except (psutil.Error, OSError):
        return False
    return True


def _apply(pid: int, action: str) -> bool:
    """Çalma alt süreçlerinin tümüne bir eylemi uygular; hiçbiri yoksa False."""
    applied = False
    for player in _players(pid):
        # Kısa devre yapılmamalı: biri başarısız olsa da diğerlerine uygulanır.
        if _try(player, action):
            applied = True
    return applied


def _terminate_players(pid: int) -> None:
    """Çalan sesleri keser.

    Sıra önemli: duraklatılmış bir süreç sonlandırma isteğini işleyemez, bu
    yüzden önce devam ettirilir. Ters sırada ffplay isteği yutup çalmayı
    sürdürüyor.
    """
    for player in _players(pid):
        _try(player, "resume")
        _try(player, "terminate")


def _try(process: psutil.Process, action: str) -> bool:
    """Süreç üzerinde bir eylemi dener; uygulanamadıysa False döner.

    Süreç iki okuma arasında ölmüş olabilir; bu olağan bir yarış, hata değil.
    Devam ettirme başarısız olsa bile sonlandırmanın denenmesi gerektiği için
    hata yutma tek tek eylemlerin çevresindedir.
    """
    try:
        getattr(process, action)()
    except (psutil.Error, OSError):
        return False
    return True


def _players(pid: int) -> list[psutil.Process]:
    """Sürecin çalma alt süreçlerini döner.

    Çalan süreci ayrı bir dosyada tutmak yerine işletim sisteminden okuruz:
    tek doğruluk kaynağı çekirdek olur, kayıt ile gerçek arasında kayma olmaz.
    """
    try:
        children = psutil.Process(pid).children(recursive=True)
    except (psutil.Error, OSError):
        return []
    return [child for child in children if _is_player(child)]


def _is_player(process: psutil.Process) -> bool:
    """Süreç, çalmayı yürüten ffplay mi?

    Uzantı ayıklanır: aynı süreç Windows'ta `ffplay.exe` adıyla görünür.
    """
    try:
        return Path(process.name()).stem.lower() == PLAYER_COMM
    except (psutil.Error, OSError):
        return False


def _is_suspended(process: psutil.Process) -> bool:
    """Süreç duraklatılmış durumda mı?"""
    try:
        return process.status() == psutil.STATUS_STOPPED
    except (psutil.Error, OSError):
        return False


def _is_pakize(pid: int) -> bool:
    """Süreç yaşıyor mu ve gerçekten Pakize mi?

    Komut satırına bakmak, kayıt bayatladıktan sonra aynı numarayı almış
    alakasız bir sürecin öldürülmesini engeller.
    """
    try:
        cmdline = psutil.Process(pid).cmdline()
    except (psutil.Error, OSError):
        return False
    return any("pakize" in arg.lower() for arg in cmdline)
