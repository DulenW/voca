"""sysaudio.py — mute macOS system output while recording. PLATFORM-SPECIFIC.

The mic picks up whatever the speakers are playing (music, a video call), and
Whisper will happily transcribe those lyrics straight into your dictation. To
stop that, we mute the system output for the duration of a recording and put
the previous state back on release.

We touch only the *mute* flag, never the volume level, so restoring is exact:
whatever the user had before comes back untouched. If they were already muted,
restore() correctly leaves them muted.

Uses `osascript` — a blocking subprocess (~100ms) — so it MUST run on the audio
worker thread, never on the hotkey tap callback (which is the main run loop and
must never block). Every call is guarded: muting is a nicety, never worth
breaking a dictation over.
"""

from __future__ import annotations

import subprocess


def _muted() -> bool | None:
    """Current system output mute state, or None if it can't be read."""
    try:
        out = subprocess.run(
            ["osascript", "-e", "output muted of (get volume settings)"],
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() == "true"
    except Exception as exc:
        print(f"[sysaudio] read mute failed: {exc}")
        return None


def _set_muted(muted: bool) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output muted {str(muted).lower()}"],
            check=True, timeout=3,
        )
    except Exception as exc:
        print(f"[sysaudio] set mute failed: {exc}")


class OutputMute:
    """Mutes system output between mute() and restore(), restoring the prior
    state. Both calls are idempotent, so a missed pair can't wedge the audio."""

    def __init__(self) -> None:
        self._prev: bool | None = None
        self._active = False

    def mute(self) -> None:
        if self._active:
            return
        # Remember the prior state so restore() puts it back exactly.
        self._prev = _muted()
        _set_muted(True)
        self._active = True

    def restore(self) -> None:
        if not self._active:
            return
        self._active = False
        # If we couldn't read the prior state, default to unmuted — never leave
        # the user's sound stuck off because of a failed read.
        _set_muted(self._prev if self._prev is not None else False)
        self._prev = None
