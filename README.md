<p align="center">
  <img src="assets/icon.png" alt="Voca" width="140">
</p>

<h1 align="center">Voca</h1>

<p align="center"><strong>Local-first, system-wide push-to-talk dictation for macOS (Apple Silicon).</strong></p>

<p align="center">
  <a href="https://github.com/DulenW/voca/releases">
    <img src="https://img.shields.io/badge/⬇%20Download-1f6feb?style=for-the-badge&logoColor=white" alt="Download">
  </a>
</p>

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
- 🔇 **Noise-aware** — an energy gate + on-device VAD (Silero) skip silence and background noise, so Whisper doesn't hallucinate text when you don't actually speak.
- 🔋 **Battery friendly** — event-driven, no polling; the mic opens only while you hold the key; ~0% CPU at idle.
- 📎 Menu bar app, no Dock icon. Optional start-at-login.

**Requires macOS on Apple Silicon (M1–M4).** ~2.5 GB disk for the models.

## Install

1. Download **`Voca.dmg`** from the [latest release](https://github.com/DulenW/voca/releases/latest).
2. Open the `.dmg` and drag **Voca** into your **Applications** folder.
3. **First launch:** the app isn't signed by Apple, so **right-click (Control-click) Voca → Open**, then confirm. You only do this once. (Double-clicking instead shows an "unidentified developer" warning.)

On first run:

- **Microphone** — click *Allow* when prompted.
- **Accessibility** — go to **System Settings → Privacy & Security → Accessibility** and enable **Voca** (needed for the global hotkey and pasting). Then quit and reopen Voca from the menu.
- Voca **downloads ~1.9 GB of models once** — the menu bar shows progress. After that it runs fully offline.

A `🎙️` icon appears in the menu bar and Voca starts automatically at login.

> **Note:** updating an unsigned app can reset its Accessibility permission. If the hotkey stops responding after an update, re-enable **Voca** under Accessibility.

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

Changes apply after you quit and reopen Voca (from the menu bar icon).

Your vocabulary and corrections are stored in
`~/Library/Application Support/Voca/voca.sqlite`.

## Updating / uninstalling

- **Update:** download the newer `Voca.dmg` and replace the app in Applications.
- **Uninstall:** quit Voca, drag **Voca** from Applications to the Trash. To also
  remove models and settings, delete `~/Library/Application Support/Voca`.

## Run from source (developers)

```bash
git clone https://github.com/DulenW/voca.git && cd voca
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_models.py     # download models (~2.5 GB, one time)
python scripts/install.py          # run as a login-item LaunchAgent
```

`scripts/uninstall.py` removes the LaunchAgent; `python main.py` runs it once
without installing.

**Build the app + `.dmg`:**

```bash
pip install -r requirements-dev.txt
bash scripts/build_app.sh          # -> dist/Voca.app and dist/Voca-1.1.0.dmg
```

## Troubleshooting

- **"Voca can't be opened — unidentified developer."** The app is unsigned.
  Right-click (Control-click) **Voca** in Applications → **Open** → confirm. You
  only need to do this once.
- **Hotkey does nothing / `⚠️` icon.** Accessibility isn't granted. Enable
  **Voca** under System Settings → Privacy & Security → Accessibility, then quit
  and reopen Voca. (After an app update you may need to re-enable it.)
- **First run is slow.** It's downloading ~1.9 GB of models once; later runs load
  from cache and start fast.
- **Right Option types accents instead.** Pick a different `hotkey` in the config.

## How it works

- **Idle:** a native macOS `CGEventTap` on the main run loop waits for the hotkey.
  No polling, no open mic — ~0% CPU.
- **Key down:** the mic opens (16 kHz mono) and buffers audio.
- **Key up:** the mic closes immediately. A speech gate (energy threshold +
  Silero VAD) drops the clip if there's no real speech; otherwise it goes to
  Whisper (kept warm in RAM).
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
| `speech.py`              | Speech gate (energy + Silero VAD) — skips silence/noise  |
| `punctuate.py`           | On-device English punctuation restoration                |
| `formatting.py`          | Capitalization, end marks, spacing                       |
| `corrections.py`         | SQLite learning layer (vocab + corrections)              |
| `inject.py`              | Clipboard + paste via Quartz — **platform-specific**     |
| `hotkey.py`              | Push-to-talk CGEventTap — **platform-specific**          |
| `config.py`              | Load/save JSON config                                    |
| `firstrun.py`            | First-launch model download                              |
| `setup.py`               | py2app build config for `Voca.app`                       |
| `scripts/build_app.sh`   | Build `Voca.app` + `.dmg`                                |
| `scripts/setup_models.py`| One-time model download (source install)                |
| `scripts/install.py`     | Install/reload the LaunchAgent (source install)          |
| `scripts/uninstall.py`   | Remove the LaunchAgent                                   |

`hotkey.py` and `inject.py` are isolated so a future Windows port only needs to
swap those two files.

## Windows

Not supported yet. The platform-specific pieces are isolated for a future port.

## License

[MIT](LICENSE) © 2026 Dulen Weerasinghe
