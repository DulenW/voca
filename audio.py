"""audio.py — microphone capture (16kHz mono float32) via sounddevice.

Battery rule (spec.md): the mic stream is opened ONLY while recording and
closed immediately on stop. It is never held open at idle. The push-to-talk
hotkey (Phase 3) drives start() on key-down and stop() on key-up; the same
Recorder also serves the fixed-duration test via record_fixed().
"""

from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # mono


class Recorder:
    """Records mic audio into a buffer between start() and stop().

    Audio arrives on a background thread via the sounddevice callback and is
    queued (not touched from the callback beyond copying), so we never do heavy
    work on the audio thread. stop() drains the queue into one float32 array.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate  # target rate handed to Whisper
        self.channels = channels
        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._capture_rate = sample_rate  # actual device rate; may differ

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:  # over/underflow etc. — log, don't crash
            print(f"[audio] stream status: {status}")
        # Copy: the buffer sounddevice hands us is reused after the callback.
        self._q.put(indata.copy())

    def start(self) -> None:
        """Open the mic stream and begin buffering. No-op if already running."""
        if self._stream is not None:
            return
        # Drain any stale frames from a previous run.
        while not self._q.empty():
            self._q.get_nowait()
        # Prefer capturing at the target rate. If the device rejects it, fall
        # back to its native rate and resample to the target rate on stop().
        try:
            self._capture_rate = self.sample_rate
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError:
            dev = sd.query_devices(kind="input")
            self._capture_rate = int(dev["default_samplerate"])
            self._stream = sd.InputStream(
                samplerate=self._capture_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

    def stop(self) -> np.ndarray:
        """Close the mic stream and return the recorded audio as 1-D float32.

        Returns an empty array if nothing was recorded.
        """
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None

        chunks: list[np.ndarray] = []
        while not self._q.empty():
            chunks.append(self._q.get_nowait())
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks, axis=0)
        if audio.ndim > 1:  # (n, 1) -> (n,)
            audio = audio.reshape(-1)
        audio = audio.astype(np.float32)
        if self._capture_rate != self.sample_rate:
            audio = _resample(audio, self._capture_rate, self.sample_rate)
        return audio

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def record_fixed(self, seconds: float) -> np.ndarray:
        """Convenience for the Phase 2 test: record for a fixed duration."""
        import time

        self.start()
        time.sleep(seconds)
        return self.stop()


def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample mono float32 audio from src_rate to dst_rate (e.g. 48k -> 16k)."""
    if src_rate == dst_rate or audio.size == 0:
        return audio
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(src_rate, dst_rate)
    up, down = dst_rate // g, src_rate // g
    return resample_poly(audio, up, down).astype(np.float32)


def default_input_name() -> str:
    """Human-readable name of the current default input device."""
    try:
        idx = sd.default.device[0]
        if idx is None or idx < 0:
            return "(system default)"
        return sd.query_devices(idx)["name"]
    except Exception as exc:  # pragma: no cover - depends on host audio
        return f"(unknown: {exc})"
