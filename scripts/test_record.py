"""Phase 2 test: record from the live mic for 5 seconds, save a WAV, transcribe.

Run it, speak while it counts down, and check the printed text. It also prints
the peak signal level so we can tell whether the mic actually captured you (a
near-zero peak means the mic is muted or Microphone permission was denied).

Usage:
    python scripts/test_record.py            # records 5 seconds
    python scripts/test_record.py 8          # records 8 seconds
"""

import os
import sys
import time

# Import from the project root regardless of where this is run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import soundfile as sf

import audio
from transcribe import transcribe

OUT_WAV = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "voca_phase2_recording.wav"
)


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0

    print(f"Input device: {audio.default_input_name()}")
    print(f"\nRecording {seconds:.0f} seconds. Speak now — say a sentence or two,")
    print("include a name or a tech term.\n")

    rec = audio.Recorder()
    rec.start()
    # First mic open triggers the macOS Microphone permission prompt.
    for remaining in range(int(seconds), 0, -1):
        print(f"  recording... {remaining}", end="\r", flush=True)
        time.sleep(1)
    clip = rec.stop()
    print("  recording... done      ")

    if clip.size == 0:
        print("\nNo audio captured. Is the mic connected / permission granted?")
        return 1

    peak = float(np.max(np.abs(clip)))
    rms = float(np.sqrt(np.mean(clip**2)))
    print(f"\nCaptured {clip.size / audio.SAMPLE_RATE:.1f}s  peak={peak:.3f}  rms={rms:.4f}")
    if peak < 0.005:
        print("WARNING: signal is nearly silent. Mic may be muted or permission")
        print("denied (System Settings > Privacy & Security > Microphone).")

    sf.write(OUT_WAV, clip, audio.SAMPLE_RATE)
    print(f"Saved WAV: {OUT_WAV}")

    print("\nTranscribing...")
    t0 = time.perf_counter()
    text = transcribe(clip)
    dt = time.perf_counter() - t0

    print("\n--- RESULT ---")
    print(f"Transcribed in {dt:.2f}s")
    print(f"Text: {text!r}")
    print("--------------")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
