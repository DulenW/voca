"""hotkey.py — pynput global hotkey listener, push-to-talk. PLATFORM-SPECIFIC.

Passive at idle: pynput's listener is event-driven, so at rest this costs
almost nothing (no polling). Hold the configured key to record, release to
transcribe. Isolated together with inject.py so the later Windows port swaps
only these two files.

Requires macOS Accessibility permission to observe keys pressed while other
apps are focused. accessibility_trusted() lets the app check and guide the
user instead of silently receiving no events.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from pynput import keyboard

# Map human-friendly config strings to pynput keys. Right Option is the spec
# default. These are the keys that make sense as a hold-to-talk trigger.
KEY_MAP = {
    "right_option": keyboard.Key.alt_r,
    "left_option": keyboard.Key.alt_l,
    "right_command": keyboard.Key.cmd_r,
    "left_command": keyboard.Key.cmd_l,
    "right_control": keyboard.Key.ctrl_r,
    "left_control": keyboard.Key.ctrl_l,
    "right_shift": keyboard.Key.shift_r,
}
DEFAULT_KEY = "right_option"


def resolve_key(name: str) -> keyboard.Key:
    """Turn a config string like 'right_option' into a pynput Key."""
    key = KEY_MAP.get(name.strip().lower().replace(" ", "_"))
    if key is None:
        raise ValueError(
            f"Unknown hotkey {name!r}. Choose one of: {', '.join(KEY_MAP)}"
        )
    return key


def accessibility_trusted() -> bool:
    """True if this process may observe global input (macOS Accessibility).

    Returns True on non-macOS or if the check can't run, so we never block a
    platform that doesn't need it.
    """
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return True


class PushToTalk:
    """Hold `key` to record; release to transcribe.

    on_press_cb / on_release_cb fire on key edges (for UI/status). on_text
    receives the final transcript. Transcription runs on a worker thread so the
    listener thread stays responsive and never drops key events.
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
    ):
        self._recorder = recorder
        self._transcribe = transcribe_fn
        self._on_text = on_text
        self._key = resolve_key(key)
        self._prompt_provider = initial_prompt_provider
        self._on_press_cb = on_press_cb
        self._on_release_cb = on_release_cb
        self._recording = False
        self._listener: Optional[keyboard.Listener] = None

    def _on_press(self, key) -> None:
        # Key auto-repeat fires on_press repeatedly while held; the flag guards
        # against starting more than once.
        if key == self._key and not self._recording:
            self._recording = True
            self._recorder.start()
            if self._on_press_cb:
                self._on_press_cb()

    def _on_release(self, key) -> None:
        if key == self._key and self._recording:
            self._recording = False
            clip = self._recorder.stop()
            if self._on_release_cb:
                self._on_release_cb()
            threading.Thread(
                target=self._handle_clip, args=(clip,), daemon=True
            ).start()

    def _handle_clip(self, clip) -> None:
        prompt = self._prompt_provider() if self._prompt_provider else None
        try:
            text = self._transcribe(clip, initial_prompt=prompt)
        except Exception as exc:  # never let a bad clip kill the listener
            print(f"[hotkey] transcription error: {exc}")
            return
        self._on_text(text)

    def start(self) -> None:
        """Start the listener (non-blocking; runs on its own thread)."""
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def run_forever(self) -> None:
        """Start and block until the listener stops (Ctrl+C)."""
        self.start()
        try:
            self._listener.join()
        except KeyboardInterrupt:
            self.stop()
