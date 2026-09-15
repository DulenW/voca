# Voca

**Local-first, system-wide push-to-talk dictation for macOS (Apple Silicon).**

Hold a hotkey, speak, release — your words are transcribed on-device and pasted
into whatever app is focused (Slack, VS Code, browser, anywhere). Everything
runs locally on the Apple GPU via [MLX](https://github.com/ml-explore/mlx). **No
audio ever leaves your machine**, and it works with wifi off. Voca learns your
custom vocabulary and corrections, so it gets better over time.

Built and tested on a MacBook Air (Apple M4).

## Features

- 🎙️ **Push-to-talk** — hold a key, speak, release. Text appears where your cursor is.
- 🔒 **100% local & private** — transcription never touches the network.
- ⚡ **Fast** — Whisper `large-v3-turbo` stays warm in memory; ~1s per dictation.
- 🧠 **Learns from you** — custom vocabulary biases spelling; corrections auto-fix recurring mistakes.
- ✍️ **Smart formatting** — English-only output, on-device punctuation (commas, periods, question marks), and context-aware capitalization (no capital when you dictate mid-sentence).
- 🔋 **Battery friendly** — event-driven, no polling; the mic opens only while you hold the key; ~0% CPU at idle.
- 📎 Menu bar app, no Dock icon. Auto-starts at login.

## Requirements

- **macOS on Apple Silicon** (M1/M2/M3/M4).
- **Python 3.11+** (this repo is built against 3.12). Install via Homebrew: `brew install python@3.12`.
- ~2.5 GB disk for the two on-device models (downloaded once).

## Install

```bash
# 1. Clone
git clone https://github.com/DulenW/voca.git
cd voca

# 2. Create the virtualenv and install dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Download the models once (needs internet; ~2.5 GB total)
python scripts/setup_models.py

# 4. Install & start as a login-item menu bar app
python scripts/install.py
```

A `🎙️` icon appears in the menu bar (`…` while it loads the first time). Voca
now starts automatically at every login.

### Grant permissions (first run)

macOS will ask for two permissions the first time you use it — both are
required, and both are handled locally:

- **Microphone** — click *Allow* when prompted.
- **Accessibility** — needed to capture the global hotkey and to paste. Go to
  **System Settings → Privacy & Security → Accessibility** and enable the entry
  for Voca / Python. Then reload: `python scripts/install.py`.

## Usage

1. Click into any text field (or just place your cursor).
2. **Hold Right Option**, speak a sentence, then **release**.
3. Your transcribed, punctuated text is pasted at the cursor.

Menu bar states: `…` loading · `🎙️` ready · `🔴` recording · `⏳` transcribing · `⚠️` error.

### Teaching Voca (the menu)

Click the `🎙️` icon:

- **Add Vocab Term…** — add names, brands, or jargon (e.g. your own name). These
  bias Whisper so it spells them correctly next time you say them.
- **Add Correction…** — map a wrong transcription to the right text. It's
  auto-applied (whole-word, case-insensitive) on every future dictation.
- **Vocabulary / Corrections** submenus — review entries; click one to delete it.
- **Edit Config…** — open the JSON config (see below).

## Configuration

Config lives at `~/Library/Application Support/Voca/config.json`:

| Key                | Default                                    | Meaning                                   |
|--------------------|--------------------------------------------|-------------------------------------------|
| `hotkey`           | `right option`                             | Hold key. Also: left option, right/left command, right/left control, right/left shift |
| `model`            | `mlx-community/whisper-large-v3-turbo`     | STT model                                 |
| `restore_clipboard`| `true`                                     | Restore your clipboard after pasting      |
| `paste_method`     | `paste`                                    | `paste` (Cmd+V) or `type` (keystrokes)    |

Changes apply after a reload: `python scripts/install.py`.

Your vocabulary and corrections are stored in
`~/Library/Application Support/Voca/voca.sqlite`.

## Updating / uninstalling

```bash
python scripts/install.py     # reload after pulling changes or editing config
python scripts/uninstall.py   # stop and remove from login (keeps models & settings)
```

To quit for the current session only, use **Voca → Quit Voca** in the menu (it
returns at next login). Run it manually without installing: `python main.py`.

## Troubleshooting

- **Menu bar icon missing / crashes as a `.app`.** Voca is intentionally
  installed as a **LaunchAgent**, not a `.app`. A thin-launcher `.app` has to
  exec an external Python, and macOS won't draw a status item for a process
  launched that way. Use `scripts/install.py`.
- **Hotkey does nothing / `⚠️`.** Accessibility isn't granted. Enable Voca/Python
  under System Settings → Privacy & Security → Accessibility, then reload.
- **First run is slow.** It's downloading models; subsequent runs load from cache.
- **Right Option types accents instead.** Pick a different `hotkey` in the config.

## How it works

- **Idle:** a native macOS `CGEventTap` on the main run loop waits for the hotkey.
  No polling, no open mic — ~0% CPU.
- **Key down:** the mic opens (16 kHz mono) and buffers audio.
- **Key up:** the mic closes immediately; audio goes to Whisper (kept warm in RAM).
- **Post-processing:** apply saved corrections → restore punctuation
  (`felflare/bert-restore-punctuation`, English) → context-aware capitalization.
- **Paste:** copy to clipboard + Cmd+V via Quartz key events, then restore your
  clipboard.

Custom vocabulary is passed to Whisper as an `initial_prompt` to bias spelling.

## Known limitations

- **Very long single dictations.** The punctuation model has a 512 word-piece
  limit (~350–400 spoken words). If you hold the key and talk past that in one
  continuous take, words beyond the limit still appear but won't get added
  commas/periods from the restoration step. Dictating in normal sentence-sized
  bursts avoids this entirely.

## Project layout

| File                     | Role                                                     |
|--------------------------|----------------------------------------------------------|
| `main.py`                | Menu bar app (rumps); wires everything together          |
| `audio.py`               | Mic capture (16 kHz mono float32)                        |
| `transcribe.py`          | mlx-whisper wrapper; loads once, English-only, offline   |
| `punctuate.py`           | On-device English punctuation restoration                |
| `formatting.py`          | Capitalization, end marks, spacing                       |
| `corrections.py`         | SQLite learning layer (vocab + corrections)              |
| `inject.py`              | Clipboard + paste via Quartz — **platform-specific**     |
| `hotkey.py`              | Push-to-talk CGEventTap — **platform-specific**          |
| `config.py`              | Load/save JSON config                                    |
| `scripts/setup_models.py`| One-time model download                                 |
| `scripts/install.py`     | Install/reload the LaunchAgent                           |
| `scripts/uninstall.py`   | Remove the LaunchAgent                                   |

`hotkey.py` and `inject.py` are isolated so a future Windows port only needs to
swap those two files.

## Windows

Not supported yet. The platform-specific pieces are isolated for a future port.

## License

[MIT](LICENSE) © 2026 Dulen Weerasinghe
