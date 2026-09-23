"""hotkey.py — push-to-talk via a native macOS CGEventTap. PLATFORM-SPECIFIC.

Why not pynput: pynput's global listener runs its event loop on its own thread
and calls the Text Input Source API (TSM) to translate keys. Inside a bundled
.app, macOS asserts that those calls happen on the main thread and hard-crashes
otherwise. So we run a CGEventTap on the MAIN run loop (rumps' loop) and only
inspect raw key codes / modifier flags — never translating to characters, so
TSM is never touched.

Event-driven and passive at idle (the tap wakes only on key events). Hold the
configured key to record, release to transcribe. Isolated with inject.py so the
Windows port swaps only these two files.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

import Quartz
import sysaudio
from CoreFoundation import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    kCFRunLoopCommonModes,
)

# Config string -> hardware key code. These are the modifier keys that make
# sense as a hold-to-talk trigger; Right Option is the spec default.
KEY_MAP = {
    "right_option": 61,
    "left_option": 58,
    "right_command": 54,
    "left_command": 55,
    "right_control": 62,
    "left_control": 59,
    "right_shift": 60,
    "left_shift": 56,
}
DEFAULT_KEY = "right_option"

# Which modifier flag each key toggles (used to tell press from release in a
# flagsChanged event). Left/right share a flag; the key code identifies which.
_MODIFIER_FLAG = {
    61: Quartz.kCGEventFlagMaskAlternate, 58: Quartz.kCGEventFlagMaskAlternate,
    54: Quartz.kCGEventFlagMaskCommand, 55: Quartz.kCGEventFlagMaskCommand,
    62: Quartz.kCGEventFlagMaskControl, 59: Quartz.kCGEventFlagMaskControl,
    60: Quartz.kCGEventFlagMaskShift, 56: Quartz.kCGEventFlagMaskShift,
}


def resolve_key(name: str) -> int:
    """Turn a config string like 'right_option' into a hardware key code."""
    code = KEY_MAP.get(name.strip().lower().replace(" ", "_"))
    if code is None:
        raise ValueError(
            f"Unknown hotkey {name!r}. Choose one of: {', '.join(KEY_MAP)}"
        )
    return code


def accessibility_trusted() -> bool:
    """True if this process may observe global input (macOS Accessibility)."""
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return True


def request_accessibility() -> bool:
    """Like accessibility_trusted(), but if not yet granted it shows the system
    "grant Accessibility" prompt and adds this app to the list (with the correct
    identity). Returns whether currently trusted."""
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        return bool(
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        )
    except Exception:
        return accessibility_trusted()


class PushToTalk:
    """Hold `key` to record; release to transcribe.

    start() must be called on the MAIN thread (it attaches the tap to the
    current run loop). CRITICAL: the tap callback runs on the main run loop, so
    it must NEVER block — audio open/close (which can hang in CoreAudio) would
    freeze the whole app and make it impossible to even quit. So the callback
    only flips a flag and posts commands to a background audio worker; all
    mic and transcription work happens off the main thread.
    """

    def __init__(
        self,
        recorder,
        transcribe_fn: Callable[..., str],
        on_text: Callable[[str], None],
        key: str = DEFAULT_KEY,
        initial_prompt_provider: Optional[Callable[[], Optional[str]]] = None,
        on_press_cb: Optional[Callable[[], None]] = None,
        on_release_cb: Optional[Callable[[], None]] = None,
        on_idle_cb: Optional[Callable[[], None]] = None,
        mute_system_audio: bool = True,
        streaming: bool = False,
    ):
        self._recorder = recorder
        self._transcribe = transcribe_fn
        self._on_text = on_text
        self._keycode = resolve_key(key)
        self._flag = _MODIFIER_FLAG[self._keycode]
        self._prompt_provider = initial_prompt_provider
        self._on_press_cb = on_press_cb
        self._on_release_cb = on_release_cb
        # Fired when all transcription work has drained and we're back to ready.
        self._on_idle_cb = on_idle_cb
        # Silence the speakers while recording so the mic doesn't pick up music
        # or video playing on this Mac. None = feature disabled.
        self._mute = sysaudio.OutputMute() if mute_system_audio else None
        self._recording = False
        self._tap = None
        self._source = None
        # FIFO of "start"/"stop" so a start is always processed before its stop.
        self._cmd_q: "queue.Queue[str]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        # Chunked (near-real-time) mode: phrases are transcribed and pasted as
        # they complete, instead of one transcription on release.
        self._streaming = streaming
        # ONE persistent worker drains this FIFO and does all transcription +
        # AI cleanup + delivery — for both batch clips and streaming phrases.
        # It MUST be a single long-lived thread: MLX (mlx-whisper and mlx-lm)
        # hangs if driven from many short-lived threads, and a single worker
        # also keeps pastes strictly in order (each lands before the next reads
        # the caret).
        self._work_q: "queue.Queue[object]" = queue.Queue()
        self._work_thread: Optional[threading.Thread] = None
        # Count of enqueued-but-not-yet-delivered phrases; when it hits 0 after
        # release we're idle. Guarded because the count is touched from the
        # capture thread (enqueue) and the chunk worker (deliver).
        self._pending = 0
        self._pending_lock = threading.Lock()
        # Last phrase transcribed this hold, fed to the next chunk as context so
        # words stay coherent across phrase boundaries. Reset on each new hold.
        self._last_text = ""

    def _tap_callback(self, proxy, etype, event, refcon):
        # Re-enable the tap if the OS disables it (timeout / heavy input).
        if etype in (Quartz.kCGEventTapDisabledByTimeout,
                     Quartz.kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )
        if keycode == self._keycode and etype == Quartz.kCGEventFlagsChanged:
            pressed = bool(Quartz.CGEventGetFlags(event) & self._flag)
            # Everything here is non-blocking: flag + a marshaled UI update +
            # a queue put. No audio calls on the main thread.
            if pressed and not self._recording:
                self._recording = True
                if self._on_press_cb:
                    self._on_press_cb()
                self._cmd_q.put("start")
            elif not pressed and self._recording:
                self._recording = False
                if self._on_release_cb:
                    self._on_release_cb()
                self._cmd_q.put("stop")
        return event  # listen-only; pass the event through untouched

    def _audio_worker(self) -> None:
        """Serialize mic open/close off the main thread. If CoreAudio ever
        hangs here, only dictation stalls — the app itself stays responsive."""
        while True:
            cmd = self._cmd_q.get()
            try:
                if cmd == "start":
                    # Fresh hold: forget the previous hold's trailing context.
                    self._last_text = ""
                    # Mute BEFORE opening the mic so nothing leaks in the gap.
                    if self._mute is not None:
                        self._mute.mute()
                    # Streaming: hand the recorder our chunk sink so phrases
                    # flow in as pauses are detected.
                    self._recorder.start(
                        on_chunk=self._enqueue_chunk if self._streaming else None
                    )
                elif cmd == "stop":
                    # stop() flushes the trailing phrase (streaming) or returns
                    # the whole clip (batch) before the mic is closed.
                    clip = self._recorder.stop()
                    # Restore the speakers as soon as the mic is closed.
                    if self._mute is not None:
                        self._mute.restore()
                    if self._streaming:
                        # Phrases were enqueued as they completed. If none were
                        # (silence held), we're already idle.
                        self._maybe_idle()
                    else:
                        # Batch: hand the whole clip to the same worker thread.
                        self._enqueue_clip(clip)
            except Exception as exc:
                print(f"[hotkey] audio {cmd} error: {exc}")
                # Never leave the speakers muted if start/stop blew up mid-way.
                if self._mute is not None:
                    self._mute.restore()

    # --- transcription + delivery (single persistent worker) ----------------
    def _enqueue_clip(self, clip) -> None:
        """Queue a clip/phrase for the work thread. Non-blocking so neither the
        capture thread (streaming) nor the audio worker (batch) ever stalls."""
        with self._pending_lock:
            self._pending += 1
        self._work_q.put(clip)

    # Streaming recorder callback (runs on the capture thread) — same path.
    _enqueue_chunk = _enqueue_clip

    def _work_loop(self) -> None:
        """Transcribe, clean up, and deliver clips one at a time, in order, all
        on THIS one thread (MLX is not safe across many threads). Serializing
        also keeps pastes ordered and lets each chunk's caret read see the
        previous one already inserted."""
        while True:
            clip = self._work_q.get()
            prompt = self._prompt_provider() if self._prompt_provider else None
            try:
                text = self._transcribe(
                    clip, initial_prompt=prompt, prev_text=self._last_text or None
                )
                if text:
                    self._last_text = text  # context for the next phrase
                self._on_text(text)
            except Exception as exc:
                print(f"[hotkey] transcription error: {exc}")
            with self._pending_lock:
                self._pending -= 1
            self._maybe_idle()

    def _maybe_idle(self) -> None:
        """Go back to ready once the key is released and the queue has drained."""
        with self._pending_lock:
            done = self._pending <= 0
        if done and not self._recording and self._on_idle_cb:
            self._on_idle_cb()

    def start(self) -> None:
        """Attach the event tap to the CURRENT run loop (must be the main one)."""
        if self._worker is None:
            self._worker = threading.Thread(target=self._audio_worker, daemon=True)
            self._worker.start()
        if self._work_thread is None:
            self._work_thread = threading.Thread(target=self._work_loop, daemon=True)
            self._work_thread.start()
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._tap_callback,
            None,
        )
        if self._tap is None:
            raise RuntimeError(
                "Could not create event tap — grant Accessibility permission."
            )
        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), self._source, kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)

    def stop(self) -> None:
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None

    def run_forever(self) -> None:
        """For standalone scripts: start the tap and run this thread's run loop."""
        self.start()
        try:
            CFRunLoopRun()
        except KeyboardInterrupt:
            self.stop()
