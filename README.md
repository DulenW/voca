# Voca

Local-first, OS-wide push-to-talk dictation for macOS (Apple Silicon).

Hold a hotkey, speak, release — the transcribed text is pasted into whatever
app is focused. Everything runs on-device (mlx-whisper on the Metal GPU). No
audio ever leaves the machine. It learns from your custom vocabulary and your
corrections over time.

Built for a MacBook Air (Apple M4). Windows is a later port — the
platform-specific parts (`hotkey.py`, `inject.py`) are isolated so only those
two files change.

## Requirements

- macOS on Apple Silicon
- Python 3.11+ (this repo is built against 3.12)

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Phase 1 — verify the model loads and transcribes

```bash
source .venv/bin/activate
python scripts/test_transcribe.py            # pipeline check with a generated tone
python scripts/test_transcribe.py you.wav    # transcribe a real WAV of your voice
```

First run downloads the model (`mlx-community/whisper-large-v3-turbo`, ~1.5GB)
to your Hugging Face cache. Subsequent runs are fast.

## Project layout

| File            | Role                                                        |
|-----------------|-------------------------------------------------------------|
| `main.py`       | rumps menu bar app; wires everything together               |
| `audio.py`      | mic capture (16kHz mono float32)                            |
| `transcribe.py` | mlx-whisper wrapper; loads model once, injects vocab        |
| `corrections.py`| SQLite learning layer (corrections + vocab)                |
| `inject.py`     | clipboard + paste — **platform-specific** (macOS)          |
| `hotkey.py`     | pynput push-to-talk listener — **platform-specific**       |
| `config.py`     | load/save JSON config                                       |

## Status

- [x] Phase 1 — Environment setup + model transcribes
- [ ] Phase 2 — Audio capture
- [ ] Phase 3 — Push-to-talk hotkey
- [ ] Phase 4 — Paste injection
- [ ] Phase 5 — Menu bar app
- [ ] Phase 6 — Learning layer
- [ ] Phase 7 — Battery pass
