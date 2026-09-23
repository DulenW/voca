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

import speech

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
LANGUAGE = "en"  # English only — never detect or output other languages

# NOTE: mlx-whisper's decoder does not implement beam search (it raises
# "Beam search decoder is not yet implemented" if beam_size is set), so we use
# greedy decoding at temperature 0 with mlx-whisper's built-in temperature
# fallback — the most accurate path this backend offers. Accuracy is gained
# instead from full-utterance context (batch mode), the optional larger model,
# and the AI cleanup layer.

# A capitalized, well-punctuated primer. Whisper continues in the style of its
# initial_prompt, so this biases it toward proper capitalization and punctuation
# (periods, commas, question marks). Custom vocab is appended to the same prompt
# so name/jargon spelling and punctuation style come from one context.
_STYLE_PRIMER = (
    "The following is a clear English transcript with correct capitalization "
    "and punctuation."
)


def _build_prompt(vocab: str | None, prev_text: str | None = None) -> str:
    """Combine the punctuation/capitalization primer with the custom vocab and,
    in streaming mode, the previous phrase — so the model has continuity across
    phrases (the tail of the prompt is the immediate preceding context)."""
    parts = [_STYLE_PRIMER]
    if vocab:
        parts.append(f"Vocabulary: {vocab}.")
    if prev_text:
        parts.append(prev_text.strip())
    return " ".join(parts)


def transcribe(
    audio: np.ndarray,
    model: str = DEFAULT_MODEL,
    initial_prompt: str | None = None,
    prev_text: str | None = None,
) -> str:
    """Transcribe 16kHz mono float32 audio to English text.

    initial_prompt carries the custom vocab; it's wrapped in a punctuation
    primer so output is properly capitalized and punctuated. prev_text is the
    previous phrase (streaming only), added as preceding context for continuity.
    Returns the stripped transcript, or "" for empty/near-silent input.
    """
    if audio is None or audio.size == 0:
        return ""
    # Speech gate: skip silence/noise so Whisper doesn't hallucinate text.
    if not speech.has_speech(audio):
        return ""
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        language=LANGUAGE,
        initial_prompt=_build_prompt(initial_prompt, prev_text),
        condition_on_previous_text=False,
    )
    return result["text"].strip()


def warm_up(model: str = DEFAULT_MODEL) -> None:
    """Load the model into memory by transcribing a tiny silent buffer.

    Called once at app start (Phase 5) so the first real dictation is fast.
    """
    silent = np.zeros(1600, dtype=np.float32)  # 0.1s of silence
    mlx_whisper.transcribe(silent, path_or_hf_repo=model)
