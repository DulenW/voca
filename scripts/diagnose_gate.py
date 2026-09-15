"""Diagnose the speech gate against your real mic/room.

    python scripts/diagnose_gate.py 3     # records 3 seconds

Run it once staying SILENT, once making NOISE (no speaking), and once while
SPEAKING normally. Paste the RMS / VAD numbers back so the thresholds can be
tuned. Nothing is transcribed or typed — it only measures.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import audio
import speech


def main() -> int:
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    speech.warm_up()

    print(f"Recording {secs:.0f}s now — hold still...")
    rec = audio.Recorder()
    rec.start()
    time.sleep(secs)
    clip = rec.stop()

    rms = float(np.sqrt(np.mean(clip.astype(np.float64) ** 2))) if clip.size else 0.0
    peak = float(np.max(np.abs(clip))) if clip.size else 0.0

    vad_segments = 0
    if speech._load_vad():
        import torch
        from silero_vad import get_speech_timestamps

        vad_segments = len(
            get_speech_timestamps(
                torch.from_numpy(clip), speech._vad, sampling_rate=16000
            )
        )

    print(f"  RMS         = {rms:.5f}   (energy threshold = {speech.SILENCE_RMS})")
    print(f"  peak        = {peak:.4f}")
    print(f"  energy pass = {rms >= speech.SILENCE_RMS}")
    print(f"  VAD speech segments = {vad_segments}")
    print(f"  => has_speech = {speech.has_speech(clip)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
