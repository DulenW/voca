"""inject.py — clipboard + paste. PLATFORM-SPECIFIC layer (macOS).

Puts the final transcript into the focused app. Default method is the
clipboard + Cmd+V (fast, handles any text); "type" synthesizes keystrokes
instead (no clipboard touched). Optionally restores the previous clipboard
after pasting, per the config.

Isolated together with hotkey.py so the later Windows port swaps only these
two files (Windows would send Ctrl+V here). Sending synthetic keys uses the
same macOS Accessibility permission the hotkey listener needs.
"""

from __future__ import annotations

import time

import pyperclip
from pynput.keyboard import Controller, Key

_kbd = Controller()


def caret_context() -> tuple[str, bool]:
    """Read the text before the caret in the focused field (macOS Accessibility).

    Returns (text_before_caret, known). known=False when the field can't be
    read (some browser/Electron fields don't expose AXValue) — the caller then
    falls back to sentence-start formatting. Platform-specific: the Windows
    port replaces this.
    """
    try:
        from HIServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateSystemWide,
            AXValueGetValue,
            kAXValueCFRangeType,
        )
    except Exception:
        return ("", False)

    try:
        system = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system, "AXFocusedUIElement", None
        )
        if err or focused is None:
            return ("", False)

        errv, value = AXUIElementCopyAttributeValue(focused, "AXValue", None)
        if errv or not isinstance(value, str):
            return ("", False)

        loc = len(value)
        errr, rng = AXUIElementCopyAttributeValue(
            focused, "AXSelectedTextRange", None
        )
        if not errr and rng is not None:
            ok, cfrange = AXValueGetValue(rng, kAXValueCFRangeType, None)
            if ok:
                loc = int(cfrange.location)

        return (value[:loc], True)
    except Exception:
        return ("", False)

# Delay after Cmd+V before restoring the old clipboard. The paste is delivered
# asynchronously; restore too soon and the app pastes the restored value. ~0.2s
# is a safe margin without a noticeable lag.
DEFAULT_RESTORE_DELAY = 0.2
# Small settle time so the clipboard write lands before we press Cmd+V.
_PRE_PASTE_DELAY = 0.05


def _send_cmd_v() -> None:
    with _kbd.pressed(Key.cmd):
        _kbd.press("v")
        _kbd.release("v")


def inject_text(
    text: str,
    method: str = "paste",
    restore_clipboard: bool = True,
    restore_delay: float = DEFAULT_RESTORE_DELAY,
) -> None:
    """Insert `text` into the focused field.

    method="paste": clipboard + Cmd+V (default). method="type": keystrokes.
    """
    if not text:
        return

    if method == "type":
        _kbd.type(text)
        return

    # method == "paste"
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(text)
    time.sleep(_PRE_PASTE_DELAY)
    _send_cmd_v()

    if restore_clipboard and previous is not None:
        time.sleep(restore_delay)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
