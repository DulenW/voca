"""Phase 1 smoke test: confirm mlx-whisper loads the model and transcribes.

Generates a short test WAV (a spoken-like tone is not real speech, so this
mainly proves the pipeline runs end to end and the model loads on the GPU).
If you pass a path to a real WAV of your own voice, it transcribes that
instead — the better test of accuracy.

Audio is fed to the model as a numpy float32 array at 16kHz, so ffmpeg is
never required.

Usage:
    python scripts/test_transcribe.py                # uses a generated tone
    python scripts/test_transcribe.py path/to/you.wav
"""

import os
import sys
import time

# Force fully-local operation: use the cached model, never hit the network.
# Without this, mlx-whisper makes a blocking HEAD request to the Hugging Face
# Hub on every load, which stalls when wifi is off or slow. The spec requires
# the app to work with wifi off, so we pin offline mode.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import soundfile as sf

MODEL = "mlx-community/whisper-large-v3-turbo"
SAMPLE_RATE = 16000


def load_audio(path: str) -> np.ndarray:
    """Load a WAV as mono float32 at 16kHz-ish. Returns a 1-D numpy array."""
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:  # stereo -> mono
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        print(f"  note: file is {sr}Hz, not {SAMPLE_RATE}Hz. Whisper resamples "
              f"internally, but real capture will be 16kHz.")
    return audio.astype(np.float32)


def make_test_tone() -> np.ndarray:
    """A 2-second 440Hz tone. Not speech — just proves the pipeline runs."""
    t = np.linspace(0, 2.0, int(SAMPLE_RATE * 2.0), endpoint=False)
    return (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def main() -> int:
    import mlx_whisper

    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"Loading audio from: {path}")
        audio = load_audio(path)
    else:
        print("No WAV given — generating a 2s test tone (pipeline check only).")
        audio = make_test_tone()

    print(f"Audio: {audio.shape[0] / SAMPLE_RATE:.1f}s, dtype={audio.dtype}")
    print(f"Loading model '{MODEL}' (first run downloads ~1.5GB)...")

    t0 = time.perf_counter()
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL)
    dt = time.perf_counter() - t0

    print("\n--- RESULT ---")
    print(f"Transcribed in {dt:.2f}s")
    print(f"Text: {result['text'].strip()!r}")
    print("--------------")
    print("\nModel loaded and transcription ran. Phase 1 pipeline works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
