**English** · [Türkçe](README.md)

# Pakize

A local tool that turns text into audio. It understands Markdown: it **does not
read code blocks** — it replaces them with a short announcement — and filters
tables, links and formatting marks according to a policy you control.

- **Sources** — file, clipboard, stdin, or a Claude Code session transcript
- **Books** — narrates EPUB/PDF/MOBI chapter by chapter, resumes if interrupted
- **Translation** — translates to a target language before speaking
- **Engines** — edge-tts (online, high quality), falls back to Piper when offline
- **Control** — read, pause and stop from a keyboard shortcut
- **Platforms** — Linux, macOS and Windows

> **Built for Turkish.** The default voice and the decimal-separator handling
> are Turkish, and so is the console output. Everything works for other
> languages too — pick a different voice with `--voice` — but a few defaults
> will look odd until you change them. Where a message matters, this document
> shows it verbatim with a translation next to it.

> **Unofficial services.** Pakize gets audio from Microsoft's Edge "Read Aloud"
> endpoint via `edge-tts`, and translation from Google's free translation
> endpoint. Neither is a **documented, officially supported API**: quotas are
> undefined, they may change or disappear at any time, and the terms of service
> of those companies do not contemplate third-party use. This tool is intended
> for personal use; evaluating it for commercial or heavy use is on you. For a
> fully local alternative that needs no network, see
> [Offline fallback: Piper](#offline-fallback-piper).

## Installation

The same four steps on Linux, macOS and Windows. About five minutes on any of
them.

**You do not need to install Python separately** — uv downloads a suitable
version if needed.

### 1. Install uv

[uv](https://docs.astral.sh/uv/) is the program that installs and runs Python
tools. Skip this step if you already have it (check with `uv --version`).

**Linux / macOS** — in a terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows** — in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation **close and reopen your terminal**; `uv` is only recognised
after that.

### 2. Install ffmpeg

Pakize uses ffmpeg to concatenate and play audio; it will not work without it.

**Linux:**

```bash
sudo apt install ffmpeg
```

**macOS** (with [Homebrew](https://brew.sh)):

```bash
brew install ffmpeg
```

**Windows** (in PowerShell):

```powershell
winget install Gyan.FFmpeg
```

> On Windows, winget updates PATH after installing but **already-open terminals
> will not see it**. Open a new PowerShell and verify with `ffmpeg -version`.

### 3. Install Pakize

**If you received a built package (`.whl` file)** — in the directory containing
the file:

```bash
uv tool install pakize-0.3.0-py3-none-any.whl
```

**If you are installing from the repository** — in the project directory:

```bash
uv tool install --editable .
```

`--editable` makes changes in the repository take effect immediately; you don't
have to reinstall after every change.

This puts the `pakize` executable in uv's tool directory — `~/.local/bin/pakize`
on Linux and macOS, `%USERPROFILE%\.local\bin\pakize.exe` on Windows.

### 4. Verify

If the `pakize` command is not recognised, the tool directory is not on PATH:

```bash
uv tool update-shell
```

Then reopen your terminal. Check that the installation works:

```bash
pakize config
```

It prints the effective settings and file paths. A real test (needs internet):

```bash
echo "Merhaba, ben Pakize." | pakize speak
```

If you hear audio, you're done.

To uninstall: `uv tool uninstall pakize`.

### Updating

**`git pull` alone is not enough.** With an `--editable` install the code
updates instantly, but if the dependency list changed, the tool environment
stays stale and you get an error like:

```
ModuleNotFoundError: No module named 'psutil'
```

Reinstalling is enough — `--force` overwrites the existing installation:

```bash
uv tool install --editable . --force
```

If you installed from a built package, run the same command with the new `.whl`:

```bash
uv tool install pakize-0.3.0-py3-none-any.whl --force
```

### Optional tools

The above is enough for basic use. Install these only if you need the
corresponding feature:

| Tool | Needed for | Linux | macOS | Windows |
|------|------------|-------|-------|---------|
| `calibre` | narrating EPUB/PDF/MOBI | `sudo apt install calibre` | `brew install --cask calibre` | `winget install calibre.calibre` |
| clipboard tool | `--clipboard` | `sudo apt install xclip` | ships with the OS (`pbpaste`) | ships with the OS (PowerShell) |
| `piper` | offline fallback engine | `uv tool install piper-tts` | same | same |

When Pakize runs into a missing tool it prints the install command **for the
platform you are on**; you can run the command from the error message as-is.

### Packaging

To produce a distributable package to send to someone else:

```bash
uv build          # writes .whl and .tar.gz under dist/
```

Whoever receives the `.whl` installs it by following steps 1-2-3 above. The
package carries only Python dependencies; `ffmpeg` and the optional tools are
still needed on each machine.

## Usage

```bash
# From a file
pakize speak notes.md

# From the clipboard
pakize speak --clipboard

# From Claude Code's last answer in this directory
pakize speak --transcript

# From a pipe
echo "Text to read" | pakize speak

# See what would be read, without producing audio
pakize speak notes.md --dry-run

# Write to a specific file, no autoplay
pakize speak notes.md -o output.mp3 --no-play
```

> If you haven't installed it system-wide, prefix commands with `uv run` and run
> them from the project directory.

If no output path is given, audio is written as `<date-time>.mp3` under the
system temporary directory and starts playing immediately — `/tmp/pakize/` on
Linux, `%TEMP%\pakize\` on Windows, and a session-specific
`/var/folders/.../pakize/` on macOS. `pakize config` shows the effective path.

Recordings accumulate there, so you can retrieve one later. Since the temporary
directory is cleared on reboot, change the `output_dir` setting if you want a
permanent archive.

### Flags

| Flag | Description |
|------|-------------|
| `-c, --clipboard` | Take text from the clipboard |
| `-t, --transcript` | Take text from a Claude Code session transcript |
| `-n, --last` | How many turns to read from the transcript (0 = all) |
| `--roles` | `assistant` (default), `user` or `all` |
| `--session` | A specific session transcript file |
| `-o, --output` | Path of the audio file to produce |
| `-v, --voice` | TTS voice (e.g. `tr-TR-AhmetNeural`) |
| `-r, --rate` | Speech rate multiplier (e.g. `1.15`) |
| `-e, --engine` | Engine to use |
| `-T, --translate` | Translate to this language before speaking (e.g. `tr`) |
| `--no-play` | Don't autoplay when the audio is ready |
| `--no-stream` | Hold the parts and play once everything is finished |
| `--dry-run` | Show the text that would be read, without producing audio |

### Other commands

```bash
pakize book book.epub         # narrate a book chapter by chapter
pakize pause                  # pause playback; resume if paused (same command)
pakize stop                   # stop the playback in progress
pakize replay                 # replay the most recently produced audio
pakize replay --list          # list recent recordings with timestamps
pakize replay --list -n 30    # show more of them
pakize voices                 # list Turkish voices
pakize voices -l all          # list every language
pakize config                 # show effective settings
pakize config --init          # create an annotated config file
```

## Translation

Translates the text before speaking it. To listen to an English book in Turkish:

```bash
pakize speak article.md --translate tr    # or -T tr
pakize book book.epub --translate tr
pakize speak -t -T en                     # hear the last answer in English
```

The source language is detected automatically; if the text is already in the
target language it is left alone. To make it permanent, put
`translate_to = "tr"` in the config.

### Where it sits

Translation runs **after parsing and before policy**. The order matters:

| Step | Why |
|------|-----|
| After parsing | Code blocks and tables never enter translation at all |
| Before policy | The "there is a 12-line code block here" announcement isn't translated twice |

Segments that get translated: prose, headings, list items, quotes. Code, tables,
links and file paths pass through untouched.

Example — English source, Turkish output:

```
Elliott Dalganın Temelleri.
Elliott Wave teorisi, piyasa fiyatlarının belirli kalıplarda ortaya çıktığını
öne sürüyor.
Burada 2 satırlık bir Python kod bloğu var.     ← code untranslated, announcement in Turkish
İkinci dalga hiçbir zaman birinci dalganın yüzde 100'ünden fazlasını geri
çekemez.
```

### Limits

Google's free endpoint **is not an official API**: the quota is undefined and
you can be temporarily blocked after many requests.

To mitigate this, lines are sent in batches — the endpoint preserves line
breaks, so dozens of segments travel in a single request. For a book that means
hundreds of requests instead of thousands. Requests go out serially with a short
wait between them, and are retried with increasing delay when rate-limited.

If you do get blocked: in book narration the chapters produced so far are kept,
and running the same command a bit later resumes where it left off.

## Book narration

Turns a long text into audio chapter by chapter. A book means 8-10 hours of
audio; instead of one file, each chapter is written separately with a playlist
alongside.

```bash
pakize book book.epub                   # chapters under book/ in the temp directory
pakize book book.pdf -o ~/Music/book    # into another directory
pakize book book.md --dry-run           # see the chapter list, produce no audio
pakize book book.epub -l 1              # only '#' headings count as chapters
```

Output:

```
book/
  01-preface.mp3
  02-chapter-one.mp3
  03-chapter-two.mp3
  book.m3u
```

### If it is interrupted

Existing chapter files are not regenerated. If production is cut short (network
dropped, you pressed Ctrl+C, the machine shut down) **run the same command
again** — it resumes where it left off:

```
Bölüm 1/24: Önsöz (atlandı)          ← "Chapter 1/24: Preface (skipped)"
Bölüm 2/24: Birinci Bölüm (atlandı)
Bölüm 3/24: İkinci Bölüm
```

Zero-byte files count as unfinished and are regenerated. To rebuild everything
from scratch, use `--force`.

### Supported formats

`.txt` and `.md` are read directly. `.epub`, `.pdf`, `.mobi` and the other
formats Calibre recognises are converted to Markdown with `ebook-convert`:

```bash
sudo apt install calibre           # Linux
brew install --cask calibre        # macOS
winget install calibre.calibre     # Windows
```

> On macOS and Windows, Calibre may not add itself to PATH. If `ebook-convert`
> isn't found, add `/Applications/calibre.app/Contents/MacOS` on macOS or
> `C:\Program Files\Calibre2` on Windows to your PATH.

Markdown is requested because it preserves headings — they are the only reliable
source of chapter boundaries.

> Conversion quality drops if the PDF has no text layer (a scanned book) or the
> page layout is multi-column. Use `--dry-run` to inspect the chapter list first.

### If no chapters are found

If the text has no headings at all, the book is split into roughly equal parts
respecting paragraph boundaries — otherwise the whole book would land in one
enormous file.

## Claude Code transcripts

Listen to the last Claude Code answer in the current directory, with no
copy-pasting:

```bash
pakize speak --transcript      # last answer
pakize speak -t -n 3           # last 3 turns
pakize speak -t --roles all    # include your own messages
pakize speak -t -n 0           # the entire session
```

The transcript is selected from `~/.claude/projects/` based on your current
directory; the most recently updated session for that project is used. To read a
different one: `--session /path/session.jsonl`.

### What gets read

The transcript file holds tool calls and their output alongside the
conversation. Only the conversation is read:

| Record | Status |
|--------|--------|
| Assistant text blocks | read |
| Messages you wrote | read with `--roles` |
| Thinking blocks (`thinking`) | skipped |
| Tool calls and results | skipped |
| Sub-agent (sidechain) conversations | skipped |
| Tool tags such as `<system-reminder>` | stripped |

A single answer can be split across dozens of records by interleaved tool calls.
Since all of that is one reply from the user's point of view, consecutive records
with the same role are merged into one turn — so `-n 1` gives you the whole
answer, not its last sentence.

With `--roles all`, a short spoken separator marks who is talking
("Kullanıcı:" = user, "Asistan:" = assistant); no separator is added when
reading a single role.

## Keyboard shortcut

This is the intended way to use it: copy text, press a key, listen.

The clipboard tool is chosen per platform: `pbpaste` on macOS, PowerShell's
`Get-Clipboard` on Windows — both ship with the OS. On Linux it depends on the
window system and has to be installed:

```bash
sudo apt install xclip      # for X11 (on Wayland: wl-clipboard)
```

Three shortcuts are enough. `pause` both pauses and resumes on its own, so no
separate "resume" key is needed:

| Name | Command | Linux/Windows | macOS |
|------|---------|---------------|-------|
| `Pakize: read clipboard` | `pakize speak --clipboard` | `Super+S` | `⌥⌘S` |
| `Pakize: pause` | `pakize pause` | `Super+Space` | `⌥⌘Space` |
| `Pakize: stop` | `pakize stop` | `Shift+Super+D` | `⇧⌥⌘D` |

### Linux (GNOME)

#### From the UI

**Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts → +** —
add one shortcut per row.

#### From the terminal

Does the same thing; the Settings screen writes to these gsettings keys too.

```bash
ROOT=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
SCHEMA=org.gnome.settings-daemon.plugins.media-keys.custom-keybinding

add() {  # add <key> <command> <binding> <name>
  KEYPATH="$ROOT/$1/"
  gsettings set "$SCHEMA:$KEYPATH" name "$4"
  gsettings set "$SCHEMA:$KEYPATH" command "$2"
  gsettings set "$SCHEMA:$KEYPATH" binding "$3"
  echo "'$KEYPATH'"
}

PATHS=$(
  add pakize-read  "pakize speak --clipboard" '<Super>s'        'Pakize: read clipboard'
  add pakize-pause "pakize pause"             '<Super>space'    'Pakize: pause'
  add pakize-stop  "pakize stop"              '<Shift><Super>d' 'Pakize: stop'
)
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
  "[$(echo $PATHS | tr ' ' ',')]"
```

> This block **rewrites the list from scratch**. If you have other custom
> shortcuts, first read the existing list with
> `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
> and append the new ones to it.

To remove them, run `gsettings reset-recursively "$SCHEMA:$KEYPATH"` for each
path and set the list to `"@as []"`.

#### Is a full path required?

Usually not: GNOME shortcuts inherit the session's `PATH`, and on Ubuntu
`~/.local/bin` is in it. Check with:

```bash
tr '\0' '\n' < /proc/$(pgrep -x gnome-shell | head -1)/environ | grep ^PATH=
```

If `~/.local/bin` is missing from the output, use full paths in the commands:
`/home/<user>/.local/bin/pakize speak --clipboard`.

#### Key conflicts

`Super+Space` is bound to switching keyboard layouts in some setups. Make sure
it is free:

```bash
gsettings get org.gnome.desktop.wm.keybindings switch-input-source
```

It is free if this returns `@as []`.

### macOS

The built-in route is Automator; no extra software needed. You create one Quick
Action per command, then assign a key.

1. **Automator → New Document → Quick Action**
2. At the top: *Workflow receives:* **no input**, *in:* **any application**
3. Drag **Run Shell Script** in from the left and enter:

```bash
$HOME/.local/bin/pakize speak --clipboard
```

4. Save it as `Pakize: read clipboard`; repeat for `pakize pause` and
   `pakize stop`.
5. **System Settings → Keyboard → Keyboard Shortcuts → Services → General** —
   assign keys next to the three Quick Actions.

> **The full path is mandatory.** Automator does not inherit your login shell's
> `PATH`; if you write just `pakize` you get "command not found" and the shortcut
> silently does nothing. Find the right path with `which pakize`.

If you want something lighter, three lines in a single
[`skhd`](https://github.com/koekeishiya/skhd) file are enough:

```
alt + cmd - s : $HOME/.local/bin/pakize speak --clipboard
alt + cmd - space : $HOME/.local/bin/pakize pause
shift + alt + cmd - d : $HOME/.local/bin/pakize stop
```

### Windows

The built-in route is a shortcut file (`.lnk`); no extra software needed.

1. `Win+R` → `shell:programs` → in the folder that opens, **right-click → New →
   Shortcut**
2. Enter as the location (with your own user name):

```
%USERPROFILE%\.local\bin\pakize.exe speak --clipboard
```

3. Save it as `Pakize: read clipboard`.
4. **Right-click the shortcut → Properties → Shortcut key**, click the field and
   press the key combination (e.g. `Ctrl+Alt+S`).
5. Repeat for `pause` and `stop`.

> With this method a console window flashes on every press. If that bothers you,
> set **Run** to *Minimized*, or use
> [AutoHotkey](https://www.autohotkey.com/):

```autohotkey
#Requires AutoHotkey v2.0
#s::Run('pakize.exe speak --clipboard', , 'Hide')
#Space::Run('pakize.exe pause', , 'Hide')
+#d::Run('pakize.exe stop', , 'Hide')
```

> Most `Win` key combinations are reserved on Windows (`Win+S` opens search).
> AutoHotkey can override them, `.lnk` shortcuts cannot — with the `.lnk` route,
> pick `Ctrl+Alt+<letter>`.

### Things worth knowing

When triggered from a shortcut there is no terminal around, so **you cannot see
the error message**. If the clipboard is empty or there is no network, nothing
happens silently. If you hear no sound, run `pakize speak -c` in a terminal to
see why.

`pause` and `stop` only manage playback that Pakize started; they never touch
other `ffplay` processes on the system. `stop` works while paused. When you run
it from a terminal, Ctrl+C stops it too.

`--transcript` is a poor fit for a shortcut: it picks the session by **working
directory**, while a shortcut runs in your home directory. If you want to bind
it, add `--session /path/session.jsonl` to the command.

These commands also manage playback you started with `pakize replay`.

If several narrations are playing at once (you started them from two different
terminals) both are managed — `stop` stops all of them, `pause` pauses all of
them:

```
$ pakize stop
Durduruldu. (2 seslendirme)      ← "Stopped. (2 narrations)"
```

`pakize book` plays no audio, it only produces files; so running
`pakize speak -c` from another terminal while a book is being produced in the
background does not conflict.

## Configuration

Settings are read from `~/.config/pakize/config.toml` on Linux and macOS, and
from `%APPDATA%\pakize\config.toml` on Windows; if `XDG_CONFIG_HOME` is set it
wins on all three. CLI flags override the file, and it works without a file at
all.

To see the effective path: `pakize config`.

To create an annotated starter file:

```bash
pakize config --init
```

The file is generated from the real defaults in the code — no second source of
truth. It never overwrites an existing file.

```toml
voice = "tr-TR-EmelNeural"       # tr-TR-AhmetNeural is also available
rate = 1.15                      # 1.0 = normal; intermediate values are fine (1.12 works)
volume = 1.0
pitch_hz = 0
max_chunk_chars = 2500           # max characters to fit into one TTS request
output_dir = "/tmp/pakize"       # where audio accumulates when no output path is given
                                 # (generated as %TEMP%\pakize on Windows)
stream = true                    # start playing as soon as the first part is ready
normalize_decimals = true        # 1.15 → 1,15 (Turkish decimal reading)

[policy]
# For each segment type: "read", "announce" or "skip"
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

### What is the policy for?

A code block set to `announce` is spoken like this:

> There is a 12-line Python code block here.

That way the code itself isn't read out but the context isn't lost either. With
`skip` the block is dropped entirely. Inline `code` and links are converted in
place, without breaking the flow of the sentence.

### File paths

`read` on the `file_path` type means reading **only the file name**, not the
whole path:

| In the text | Read as |
|-------------|---------|
| `src/pakize/models.py` | "models.py" |
| `~/.config/pakize/config.toml` | "config.toml" |

"ess-are-see slash pakize slash models dot pee why" is not something anyone can
listen to. If you want the path dropped entirely, set `file_path = "skip"`.

To count as a path, a string needs at least one `/` and a final component with
an extension — that way expressions like `and/or` or `TR/EN` are left alone.

## Offline fallback: Piper

`edge-tts` depends on the internet and on an unofficial Microsoft endpoint.
Piper runs locally; when there is no network or the service breaks, Pakize falls
back to it on its own and says so:

```
Not: edge motoru çalışmadı, piper kullanıldı.
← "Note: the edge engine failed, piper was used."
```

Installation has two parts — the executable and a voice model:

```bash
uv tool install piper-tts
```

Download a voice model from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) (the `.onnx`
and its neighbouring `.onnx.json` must stay together), then write it into the
config:

```toml
fallback_engine = "piper"
piper_model = "/path/tr_TR-dfki-medium.onnx"
piper_binary = "/path/piper"       # searched on PATH if empty
```

> On Windows, if you write paths with backslashes in TOML, **double them**
> (`"C:\\voices\\tr_TR-dfki-medium.onnx"`) or use forward slashes
> (`"C:/voices/tr_TR-dfki-medium.onnx"`) — a single backslash starts an escape
> sequence in TOML. The file produced by `pakize config --init` handles this
> itself.

To use only Piper, set `engine = "piper"` or pass `--engine piper`.

Piper produces WAV; if the target file is `.mp3` it is converted during
concatenation. The rate setting comes from the same `rate` field for both
engines — since Piper expresses speed as duration, the value is inverted
internally.

If neither engine works, **the primary engine's** error is shown; the fallback's
"not installed" message would have hidden the real problem.

## Decimal numbers

In Turkish the decimal separator is a comma. Written as `1.15`, it is read
incorrectly when it reaches a TTS engine under Turkish rules, so it is converted
to `1,15`.

Version numbers match the same pattern: `Python 3.10` → "three comma ten". There
is no way to tell the two apart by looking at the text. If version numbers matter
more to you, set `normalize_decimals = false`.

Multi-dot expressions such as `1.2.3`, `192.168.1.1` and `09.08.2026` are left
untouched.

## Streaming playback

By default audio starts playing **as soon as the first part is ready**; the
remaining parts keep being produced in the background. For a long text, the time
you wait for the first sound is the duration of the first part only, not of the
whole text.

The archive file is still written in full. If you want the audio to play as a
single piece from start to finish, use `--no-stream` or set `stream = false` in
the config.

## About speed

`edge-tts` takes the rate as a percentage and has no limit on intermediate
values. So you are not restricted to the preset steps like 1.25 / 1.5 you see on
`edge-tts.com`; both `rate = 1.15` and `rate = 1.12` work. The default is
**1.15**.

## Architecture

```
text
  → parsing/markdown.py   block detection (code, table, heading, list, quote)
  → parsing/policy.py     read/announce/skip per type + inline normalization
  → chunking.py           packing at sentence boundaries, up to a character limit
  → engines/              TTS adapter (edge; a fallback engine can be plugged in)
  → audio.py              concatenation and playback via ffmpeg
```

Every interface (CLI, clipboard shortcut, transcript reader, web panel) calls
`pipeline.synthesize`; the business logic is not duplicated anywhere else.

### Where do the platform differences live?

The whole pipeline above runs the same code on all three platforms. Everything
that has to ask the system itself is collected in `platforms.py` — where
settings are written, where the temporary directory is, how to install a missing
tool. No other module looks at `sys.platform`.

Two more places differ in behaviour, both encapsulated:

- **Process control** (`runtime.py`) — `psutil` is used to find, pause and stop
  the playing `ffplay`. Pausing is `SIGSTOP` on POSIX and `NtSuspendProcess` on
  Windows; `psutil` hides both behind one call. On every platform `pakize stop`
  **silences the audio first and terminates the process second**: on Windows,
  terminating a process does not run its signal handler, so the main process
  would die before it could stop its own `ffplay` and the audio would keep
  playing orphaned.
- **Clipboard** (`sources/clipboard.py`) — the OS's own tool is always tried
  first, then the tool matching the window system.

## Tests

Tests are hermetic: no network access, no real TTS calls and no `ffmpeg`
execution; the engine and concatenation are patched.

```bash
uv run pytest
```

## License

[MIT](LICENSE) — use it, change it, distribute it; the only condition is keeping
the copyright notice.

Dependency licenses are separate and subject to their own terms:

| Dependency | License |
|------------|---------|
| `edge-tts` | LGPL-3.0 |
| `typer` | MIT |
| `psutil` | BSD-3-Clause |
| `tomli` | MIT |

`edge-tts` is LGPL, but Pakize does not bundle it into the package; it is
installed as a separate package and imported. LGPL explicitly permits this use,
which is why Pakize's own code can stay MIT.
