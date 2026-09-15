"""speech.py — decide whether a captured clip actually contains speech.

Whisper confidently hallucinates text ("Thank you.", ".") from silence or
noise, so we gate before transcribing with two cheap, local layers:

  1. Energy gate — skip clips quieter than SILENCE_RMS (held key, no speech).
  2. Silero VAD — a tiny on-device model that detects human speech; skip clips
     with none (background noise, fans, tones).

If the VAD model can't load, we fall back to the energy gate alone (never
over-filter real speech).
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
SILENCE_RMS = 0.006  # clips quieter than this RMS are treated as silence

_vad = None
_available = False


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))


def _load_vad() -> bool:
    global _vad, _available
    if _vad is not None:
        return _available
    try:
        # silero_vad imports torchaudio at module top, but only uses it in
        # read_audio/save_audio (file I/O) — which we never call (we pass a
        # tensor). torchaudio's native lib fails to load inside a py2app bundle,
        # so stub it if it won't import, letting silero_vad load cleanly.
        import sys
        import types

        try:
            __import__("torchaudio")  # use the real one when it loads
        except Exception:
            sys.modules["torchaudio"] = types.ModuleType("torchaudio")

        from silero_vad import load_silero_vad

        _vad = load_silero_vad()
        _available = True
    except Exception as exc:
        print(f"[speech] VAD unavailable, using energy gate only: {exc}")
        _vad = False  # sentinel: don't retry
        _available = False
    return _available


def warm_up() -> None:
    _load_vad()


def has_speech(audio: np.ndarray) -> bool:
    """True if the clip likely contains human speech."""
    if audio is None or audio.size == 0:
        return False
    if _rms(audio) < SILENCE_RMS:
        return False  # silence
    if not _load_vad():
        return True  # VAD missing → let it through rather than drop real speech

    import torch
    from silero_vad import get_speech_timestamps

    segments = get_speech_timestamps(
        torch.from_numpy(audio), _vad, sampling_rate=SAMPLE_RATE
    )
    return len(segments) > 0
