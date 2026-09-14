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

import threading
from typing import Callable, Optional

import Quartz
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


class PushToTalk:
    """Hold `key` to record; release to transcribe.

    start() must be called on the MAIN thread (it attaches the tap to the
    current run loop). on_text receives the final transcript; transcription
    runs on a worker thread so the run loop stays responsive.
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
        self._keycode = resolve_key(key)
        self._flag = _MODIFIER_FLAG[self._keycode]
        self._prompt_provider = initial_prompt_provider
        self._on_press_cb = on_press_cb
        self._on_release_cb = on_release_cb
        self._recording = False
        self._tap = None
        self._source = None

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
            if pressed and not self._recording:
                self._recording = True
                self._recorder.start()
                if self._on_press_cb:
                    self._on_press_cb()
            elif not pressed and self._recording:
                self._recording = False
                clip = self._recorder.stop()
                if self._on_release_cb:
                    self._on_release_cb()
                threading.Thread(
                    target=self._handle_clip, args=(clip,), daemon=True
                ).start()
        return event  # listen-only; pass the event through untouched

    def _handle_clip(self, clip) -> None:
        prompt = self._prompt_provider() if self._prompt_provider else None
        try:
            text = self._transcribe(clip, initial_prompt=prompt)
        except Exception as exc:
            print(f"[hotkey] transcription error: {exc}")
            return
        self._on_text(text)

    def start(self) -> None:
        """Attach the event tap to the CURRENT run loop (must be the main one)."""
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
