"""transcribe.py — mlx-whisper wrapper.

Feeds captured audio (numpy float32, 16kHz) straight to the model, so ffmpeg
is never needed. Runs fully local: HF_HUB_OFFLINE is pinned so the model loads
from the on-disk cache with no network call (works with wifi off, per spec.md).

mlx_whisper caches the loaded model per repo internally, so repeated calls
reuse the warm model. Phase 5 formalizes an explicit warm-up at app start.
"""

from __future__ import annotations

import os

# Must be set before mlx_whisper/huggingface_hub import, or the Hub does a
# blocking network check on load that stalls when wifi is off/slow.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import mlx_whisper

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe(
    audio: np.ndarray,
    model: str = DEFAULT_MODEL,
    initial_prompt: str | None = None,
) -> str:
    """Transcribe 16kHz mono float32 audio to text.

    initial_prompt biases spelling (Phase 6 passes the custom vocab here).
    Returns the stripped transcript, or "" for empty/near-silent input.
    """
    if audio is None or audio.size == 0:
        return ""
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        initial_prompt=initial_prompt,
    )
    return result["text"].strip()


def warm_up(model: str = DEFAULT_MODEL) -> None:
    """Load the model into memory by transcribing a tiny silent buffer.

    Called once at app start (Phase 5) so the first real dictation is fast.
    """
    silent = np.zeros(1600, dtype=np.float32)  # 0.1s of silence
    mlx_whisper.transcribe(silent, path_or_hf_repo=model)
