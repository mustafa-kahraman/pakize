"""Çalmakta olan seslendirmenin süreç kaydı, okuma kuyruğu ve denetimi.

`pakize stop` ve `pakize pause`, çalmayı başlatan sürece ulaşabilmek için bu
kaydı okur. Kayıt geçici dizin altında tutulur; oturum kapanınca işletim
sistemi temizler.

Kayıt aynı zamanda bir kuyruktur: her çalacak süreç sıraya girer ve kendinden
eski yaşayan kayıt kalmayana kadar bekler; böylece iki Pakize asla üst üste
çalmaz. Sıra, kayda yazılan zaman damgasıyla belirlenir (eşitlikte küçük
süreç numarası önde); dosya değişiklik zamanı dosya sistemine göre kaba
olabildiği için kullanılmaz. Kilit yoktur: önce kaydol, sonra sıraya bak —
Windows'ta POSIX kilitleri yok, bu yol her yerde çalışır.

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
    (state_dir(name) / str(pid)).unlink(missing_ok=True)


def entries(name: str = STATE_NAME) -> list[Entry]:
    """Kayıtlı ve hâlâ yaşayan Pakize süreçleri; sıra düzeninde, en eski önde.

    En öndeki çalandır, gerisi bekler. Bayat kayıtlar sessizce temizlenir.
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
            path.unlink(missing_ok=True)
            continue
        alive.append(_read_entry(pid, path))

    return sorted(alive, key=lambda entry: (entry.registered_ns, entry.pid))


def running_pids(name: str = STATE_NAME) -> list[int]:
    """Kayıtlı ve hâlâ yaşayan Pakize süreçleri; sıra düzeninde, çalan önde."""
    return [entry.pid for entry in entries(name)]


def running_pid() -> int | None:
    """Sıranın başındaki, yani çalmakta olan süreç; yoksa None."""
    pids = running_pids()
    return pids[0] if pids else None


def wait_for_turn(pid: int, name: str = STATE_NAME) -> None:
    """Sürecin önündeki kayıtlar bitene kadar bekler.

    Kendi kaydı silinmişse de döner: `pakize stop --all` süreci zaten
    sonlandırıyordur, burada takılı kalmanın anlamı yok.
    """
    while True:
        pids = running_pids(name)
        if pid not in pids or pids[0] == pid:
            return
        time.sleep(QUEUE_POLL_SECONDS)


def earlier_duplicate(pid: int, name: str = STATE_NAME) -> bool:
    """Sırada bu süreçten önce aynı metni taşıyan bir kayıt var mı?

    Önce kaydolup sonra bakmak yarışı belirli kılar: aynı anda giren iki
    süreçten sıralamada arkada kalan tekrar sayılır, öndeki kalır. Metinsiz
    kayıtlar hiçbir şeyle eşleşmez.
    """
    queue = entries(name)
    own = next((entry for entry in queue if entry.pid == pid), None)
    if own is None or own.text_hash is None:
        return False
    return any(
        entry.text_hash == own.text_hash for entry in queue[: queue.index(own)]
    )


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
