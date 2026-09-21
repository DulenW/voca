"""audio.py — microphone capture (16kHz mono float32) via sounddevice.

Battery rule (spec.md): the mic stream is opened ONLY while recording and
closed immediately on stop. It is never held open at idle. The push-to-talk
hotkey drives start() on key-down and stop() on key-up.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # mono
_BLOCKSIZE = 1024  # frames per blocking read (~64ms at 16kHz)


class Recorder:
    """Records mic audio into a buffer between start() and stop().

    Uses a BLOCKING read loop on a dedicated thread (not a portaudio callback).
    A callback-based stream must acquire the GIL from the CoreAudio IO thread,
    which deadlocks when the stream is closed while the GIL is held — reliably so
    inside a bundled app with many other native threads. Blocking reads release
    the GIL and let us tear the stream down cleanly.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate  # target rate handed to Whisper
        self.channels = channels
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._frames: list[np.ndarray] = []
        self._capture_rate = sample_rate  # actual device rate; may differ

    def _open_stream(self) -> None:
        # Prefer the target rate; if the device rejects it, fall back to its
        # native rate and resample on stop().
        try:
            self._capture_rate = self.sample_rate
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=self.channels, dtype="float32"
            )
            self._stream.start()
        except sd.PortAudioError:
            dev = sd.query_devices(kind="input")
            self._capture_rate = int(dev["default_samplerate"])
            self._stream = sd.InputStream(
                samplerate=self._capture_rate, channels=self.channels, dtype="float32"
            )
            self._stream.start()

    def _read_loop(self) -> None:
        # Poll read_available and only read what's ready, so read() never blocks
        # waiting for the mic. This lets the loop check the stop flag promptly and
        # tear down cleanly even if the mic delivers no data.
        while not self._stop_flag.is_set():
            try:
                avail = self._stream.read_available
                if avail >= _BLOCKSIZE:
                    data, _overflowed = self._stream.read(_BLOCKSIZE)
                    self._frames.append(data.copy())
                else:
                    time.sleep(0.01)
            except Exception as exc:  # stream closing / device error
                print(f"[audio] read stopped: {exc}")
                break
        # Drain whatever remains so we don't clip the end of speech.
        try:
            remaining = self._stream.read_available
            if remaining > 0:
                data, _ = self._stream.read(remaining)
                self._frames.append(data.copy())
        except Exception:
            pass

    def start(self) -> None:
        """Open the mic stream and begin buffering. No-op if already running."""
        if self._stream is not None:
            return
        self._frames = []
        self._stop_flag = threading.Event()
        self._open_stream()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> np.ndarray:
        """Stop the read loop, close the mic, and return 1-D float32 audio.

        Returns an empty array if nothing was recorded. Deadlock-free: the read
        thread exits within one block, then we close the (idle) stream.
        """
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # abort() stops immediately without waiting for buffers to drain (less
        # likely to block than stop()). Guard each call so one failure doesn't
        # skip the rest — we've already captured the frames.
        stream = self._stream
        self._stream = None
        for teardown in (stream.abort, stream.close):
            try:
                teardown()
            except Exception as exc:
                print(f"[audio] {teardown.__name__} error: {exc}")

        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames, axis=0)
        self._frames = []
        if audio.ndim > 1:  # (n, 1) -> (n,)
            audio = audio.reshape(-1)
        audio = audio.astype(np.float32)
        if self._capture_rate != self.sample_rate:
            audio = _resample(audio, self._capture_rate, self.sample_rate)
        return audio


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
