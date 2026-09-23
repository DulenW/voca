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
into whatever app is focused (Slack, VS Code, browser, anywhere). Transcription
**and** the AI cleanup run locally on the Apple GPU via
[MLX](https://github.com/ml-explore/mlx), so **your audio never leaves your
machine** and it works with wifi off. Voca learns your custom vocabulary and
corrections, so it gets better over time.

Built and tested on a MacBook Air (Apple M4).

## Features

- 🎙️ **Push-to-talk** — hold a key, speak, release. Text appears where your cursor is.
- 🧠 **AI cleanup & smart formatting** — a small on-device AI rewrites your dictation into clean prose: removes fillers (um/uh), fixes grammar and homophones, and formats numbers, currency, dates, emails, and lists — while staying faithful to what you said. Free and offline; an optional cloud model (your own API key) is available for the highest quality.
- 🗣️ **Hears soft voices** — automatically boosts quiet/low-volume speech so a soft voice is picked up reliably.
- 🔒 **Private & offline by default** — your audio never leaves your Mac, and the default AI cleanup runs on-device too. (The only exception is the *optional* cloud cleanup, which is **off** unless you add your own API key.)
- ⚡ **Fast** — Whisper `large-v3-turbo` stays warm in memory; ~1–2s per dictation.
- 🧠 **Learns from you** — custom vocabulary biases spelling; corrections auto-fix recurring mistakes.
- 🔇 **Mutes distractions** — silences your Mac's own audio while you hold the key, so music or a video playing on your speakers isn't captured and transcribed.
- ⏱️ **Real-time option** — an optional streaming mode pastes text phrase-by-phrase as you speak (accuracy-first batch mode is the default).
- 🔇 **Noise-aware** — an energy gate + on-device VAD (Silero) skip silence and background noise, so Whisper doesn't hallucinate text when you don't actually speak.
- 🔋 **Battery friendly** — event-driven, no polling; the mic opens only while you hold the key; ~0% CPU at idle.
- 📎 Menu bar app, no Dock icon. Optional start-at-login.

**Requires macOS on Apple Silicon (M1–M4).** ~3.4 GB disk for the models (speech + on-device AI cleanup).

## Install

1. Download **`Voca.dmg`** from the [latest release](https://github.com/DulenW/voca/releases/latest).
2. Open the `.dmg` and drag **Voca** into your **Applications** folder.
3. **First launch:** the app isn't signed by Apple, so **right-click (Control-click) Voca → Open**, then confirm. You only do this once. (Double-clicking instead shows an "unidentified developer" warning.)

On first run:

- **Microphone** — click *Allow* when prompted.
- **Accessibility** — go to **System Settings → Privacy & Security → Accessibility** and enable **Voca** (needed for the global hotkey and pasting). Then quit and reopen Voca from the menu.
- Voca **downloads ~3.4 GB of models once** (speech + on-device AI cleanup) — the menu bar shows progress; downloads are resumable, so a slow connection won't lose progress. After that it runs fully offline.

A `🎙️` icon appears in the menu bar and Voca starts automatically at login.

> **Note:** updating an unsigned app can reset its Accessibility permission. If the hotkey stops responding after an update, re-enable **Voca** under Accessibility.

## Usage

1. Click into any text field (or just place your cursor).
2. **Hold Right Option**, speak a sentence, then **release**.
3. Your transcribed, punctuated text is pasted at the cursor.

Menu bar states: `…` loading · `🎙️` ready · `🔴` recording · `⏳` transcribing / cleaning up · `⚠️` error.

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

| Key                  | Default                                  | Meaning                                   |
|----------------------|------------------------------------------|-------------------------------------------|
| `hotkey`             | `right option`                           | Hold key. Also: left option, right/left command, right/left control, right/left shift |
| `model`              | `mlx-community/whisper-large-v3-turbo`   | STT model (set to `mlx-community/whisper-large-v3` for higher accuracy, slower) |
| `restore_clipboard`  | `true`                                   | Restore your clipboard after pasting      |
| `paste_method`       | `paste`                                  | `paste` (Cmd+V) or `type` (keystrokes)    |
| `mute_system_audio`  | `true`                                   | Mute your Mac's audio while recording so the mic doesn't capture music/video |
| `boost_quiet_speech` | `true`                                   | Auto-amplify soft/low-volume voices before transcription |
| `streaming`          | `false`                                  | `false` = transcribe the whole clip on release (accuracy-first). `true` = near-real-time, phrase-by-phrase while you hold |
| `cleanup_backend`    | `local`                                  | AI cleanup: `local` (free, on-device), `cloud` (Anthropic, your own key), or `off` (rule-based punctuation only) |
| `cleanup_model_local`| `mlx-community/Qwen2.5-3B-Instruct-4bit` | On-device cleanup model (downloaded once) |
| `cleanup_model_cloud`| `claude-haiku-4-5-20251001`              | Model used only when `cleanup_backend` is `cloud` |
| `anthropic_api_key`  | `""`                                     | Only for `cloud`; the `ANTHROPIC_API_KEY` env var takes precedence |

Changes apply after you quit and reopen Voca (from the menu bar icon).

### AI cleanup & privacy

By default, cleanup runs **on-device** with a small local model — free, offline, and
private. If you prefer the highest quality and don't mind it being a paid, online
service, set `cleanup_backend` to `cloud` and provide your own Anthropic API key
(via the `ANTHROPIC_API_KEY` environment variable or the `anthropic_api_key` config
key). In cloud mode, your **transcribed text** (never your audio) is sent to Anthropic
for cleanup. Cloud is **off** unless you explicitly enable it. Set `cleanup_backend`
to `off` to skip AI cleanup entirely and use the lightweight rule-based punctuation.

Your vocabulary and corrections are stored in
`~/Library/Application Support/Voca/voca.sqlite`.

## Updating / uninstalling

- **Update:** download the newer `Voca.dmg` and replace the app in Applications.
- **Uninstall:** click the menu bar icon → **Uninstall Voca…**. It deletes the
  downloaded models (~3.4 GB) and moves Voca and your settings to the Trash, then
  quits — empty the Trash to reclaim the space. (Dragging the app to the Trash by
  itself leaves the models behind, since macOS runs no cleanup code at that point.)

## Run from source (developers)

```bash
git clone https://github.com/DulenW/voca.git && cd voca
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_models.py     # download models (~3.7 GB, one time)
python scripts/install.py          # run as a login-item LaunchAgent
```

`scripts/uninstall.py` removes the LaunchAgent; `python main.py` runs it once
without installing.

**Build the app + `.dmg`:**

```bash
pip install -r requirements-dev.txt
bash scripts/build_app.sh          # -> dist/Voca.app and dist/Voca-1.4.0.dmg
```

## Troubleshooting

- **"Voca can't be opened — unidentified developer."** The app is unsigned.
  Right-click (Control-click) **Voca** in Applications → **Open** → confirm. You
  only need to do this once.
- **Hotkey does nothing / `⚠️` icon.** Accessibility isn't granted. Enable
  **Voca** under System Settings → Privacy & Security → Accessibility, then quit
  and reopen Voca. (After an app update you may need to re-enable it.)
- **First run is slow.** It's downloading ~3.4 GB of models once (speech + AI
  cleanup); downloads are resumable, so quitting and reopening resumes where it
  left off. Later runs load from cache and start fast.
- **Right Option types accents instead.** Pick a different `hotkey` in the config.

## How it works

- **Idle:** a native macOS `CGEventTap` on the main run loop waits for the hotkey.
  No polling, no open mic — ~0% CPU.
- **Key down:** your Mac's audio is muted (optional) and the mic opens (16 kHz
  mono) and buffers audio.
- **Key up:** the mic closes immediately and your audio is unmuted. Quiet clips
  are auto-boosted, then a speech gate (energy threshold + Silero VAD) drops the
  clip if there's no real speech; otherwise it goes to Whisper (kept warm in RAM).
- **Post-processing:** apply saved corrections → **AI cleanup** (on-device by
  default: grammar, fillers, and smart formatting; or rule-based punctuation when
  cleanup is off) → context-aware capitalization/spacing.
- **Paste:** copy to clipboard + Cmd+V via Quartz key events, then restore your
  clipboard.

All transcription, AI cleanup, and pasting run on a single background worker
thread, so the menu bar and Quit always stay responsive. Custom vocabulary is
passed to Whisper as an `initial_prompt` (and to the cleanup model) to bias
spelling.

## Known limitations

- **Very long single dictations (rule-based mode only).** When AI cleanup is set
  to `off`, the rule-based punctuation model has a 512 word-piece limit (~350–400
  spoken words); words beyond that still appear but won't get added
  commas/periods. AI cleanup (the default) doesn't have this limit. Either way,
  dictating in normal sentence-sized bursts works best.

## Project layout

| File                     | Role                                                     |
|--------------------------|----------------------------------------------------------|
| `main.py`                | Menu bar app (rumps); wires everything together          |
| `audio.py`               | Mic capture (16 kHz mono float32) + live phrase chunking |
| `chunker.py`             | Splits a live stream into phrases (streaming mode)       |
| `transcribe.py`          | mlx-whisper wrapper; quiet-boost, loads once, offline    |
| `speech.py`              | Speech gate (energy + Silero VAD) — skips silence/noise  |
| `enhance.py`             | AI cleanup + smart formatting (local MLX / cloud / off)  |
| `punctuate.py`           | Rule-based English punctuation (used when cleanup is off)|
| `formatting.py`          | Capitalization, end marks, spacing                       |
| `corrections.py`         | SQLite learning layer (vocab + corrections)              |
| `inject.py`              | Clipboard + paste via Quartz — **platform-specific**     |
| `hotkey.py`              | Push-to-talk CGEventTap — **platform-specific**          |
| `sysaudio.py`            | Mute system output while recording — **platform-specific**|
| `config.py`              | Load/save JSON config                                    |
| `firstrun.py`            | First-launch model download                              |
| `uninstall.py`           | "Uninstall Voca…" — remove models + app (to Trash)       |
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
