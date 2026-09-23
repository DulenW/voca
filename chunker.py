"""chunker.py — split a live mic stream into phrase-sized chunks at pauses.

For near-real-time ("chunked") dictation. While the key is held, the recorder
feeds this one audio block at a time; whenever the speaker pauses (a short
stretch of silence after speech) or a phrase runs long, it emits the buffered
phrase so it can be transcribed and pasted while the user keeps talking.

Energy-based on purpose: cheap enough to run on the capture thread, and
rate-independent (RMS doesn't care about the sample rate), so it works whether
the device captures at 16k or 48k. Each phrase is a complete utterance bounded
by silence, so per-chunk transcription, punctuation, and vocab all behave the
same as the batch path — the text just arrives in pieces.

Pure and single-threaded: feed()/flush() are always called from one thread (the
recorder's capture loop), so no locking is needed here.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

# Tuned for push-to-talk dictation. A silence run longer than PAUSE_SEC after
# speech ends a phrase. A phrase never grows past MAX_PHRASE_SEC, which bounds
# latency and stays well under Whisper's 30s window even for run-on speech.
# MIN_SPEECH_SEC keeps very short fragments from being transcribed alone (they
# merge into the next phrase instead) — Whisper is far more accurate with a bit
# more context.
PAUSE_SEC = 0.9
MAX_PHRASE_SEC = 12.0
MIN_SPEECH_SEC = 1.0
# Match speech.py's energy gate so "is this speech?" means the same thing here.
SILENCE_RMS = 0.006


def _rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block.astype(np.float64)))))


class PhraseChunker:
    """Emits phrase chunks via on_chunk(np.ndarray) as pauses are detected.

    feed(block) on each captured block; flush() once at the end to emit any
    trailing speech. Chunks are raw capture-rate float32 — the recorder
    resamples them to 16k before handing them on.
    """

    def __init__(self, on_chunk: Callable[[np.ndarray], None], capture_rate: int):
        self._on_chunk = on_chunk
        self._buf: list[np.ndarray] = []
        self._silence_samples = 0  # length of the current trailing-silence run
        self._speech_samples = 0  # total speech buffered since the last emit
        self._had_speech = False  # any speech buffered since the last emit?
        self._pause_samples = int(PAUSE_SEC * capture_rate)
        self._max_samples = int(MAX_PHRASE_SEC * capture_rate)
        self._min_speech_samples = int(MIN_SPEECH_SEC * capture_rate)
        self._buf_samples = 0

    def feed(self, block: np.ndarray) -> None:
        block = block.reshape(-1)
        self._buf.append(block)
        self._buf_samples += block.size

        if _rms(block) >= SILENCE_RMS:
            self._had_speech = True
            self._speech_samples += block.size
            self._silence_samples = 0
        else:
            self._silence_samples += block.size

        # End the phrase on a long-enough pause AFTER enough speech to be worth
        # transcribing on its own, or force it out at the length cap so a
        # run-on sentence still flows.
        paused = (
            self._silence_samples >= self._pause_samples
            and self._speech_samples >= self._min_speech_samples
        )
        if self._had_speech and (paused or self._buf_samples >= self._max_samples):
            self._emit()

    def flush(self) -> None:
        """Emit any trailing speech; drop a buffer that's pure silence."""
        if self._had_speech:
            self._emit()
        else:
            self._reset()

    def _emit(self) -> None:
        if not self._buf:
            self._reset()
            return
        chunk = np.concatenate(self._buf, axis=0).astype(np.float32)
        self._reset()
        self._on_chunk(chunk)

    def _reset(self) -> None:
        self._buf = []
        self._buf_samples = 0
        self._silence_samples = 0
        self._speech_samples = 0
        self._had_speech = False
