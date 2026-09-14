"""main.py — the Voca menu bar app. Wires everything together.

Loads the Whisper model once at startup and keeps it warm for the whole
session. A pynput listener (passive at idle, no polling) drives push-to-talk;
on release the audio is transcribed and pasted into the focused app.

Menu bar status:  …=loading  🎙️=ready  🔴=recording  ⏳=transcribing  ⚠️=error

Run:  python main.py   (quit from the menu, or Ctrl+C in the terminal)
"""

from __future__ import annotations

import subprocess
import threading

import rumps
from PyObjCTools import AppHelper

import audio
import config
import hotkey
import inject
from transcribe import transcribe, warm_up

LOADING, READY, REC, BUSY, ERROR = "…", "🎙️", "🔴", "⏳", "⚠️"


class VocaApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Voca", title=LOADING, quit_button="Quit Voca")
        self.cfg = config.load()
        self.recorder = audio.Recorder()
        self._ptt: hotkey.PushToTalk | None = None

        self.status_item = rumps.MenuItem("Loading model…")
        self.menu = [
            self.status_item,
            None,  # separator
            rumps.MenuItem("Edit Config…", callback=self._edit_config),
        ]

        # Load the model off the main thread so the menu bar appears instantly.
        threading.Thread(target=self._startup, daemon=True).start()

    # --- main-thread UI helpers (marshaled; no polling) ---------------------
    def _ui(self, func, *args) -> None:
        AppHelper.callAfter(func, *args)

    def _set_title(self, t: str) -> None:
        self.title = t

    def _set_status(self, s: str) -> None:
        self.status_item.title = s

    # --- startup ------------------------------------------------------------
    def _startup(self) -> None:
        try:
            warm_up(self.cfg["model"])
        except Exception as exc:
            self._ui(self._set_title, ERROR)
            self._ui(self._set_status, f"Model failed to load: {exc}")
            return

        self._ptt = hotkey.PushToTalk(
            recorder=self.recorder,
            transcribe_fn=self._transcribe,
            on_text=self._on_text,
            key=self.cfg["hotkey"],
            on_press_cb=self._on_press,
            on_release_cb=self._on_release,
        )
        self._ptt.start()

        if not hotkey.accessibility_trusted():
            self._ui(self._set_title, ERROR)
            self._ui(
                self._set_status,
                "Grant Accessibility (System Settings) then restart",
            )
            return

        self._ui(self._set_title, READY)
        self._ui(self._set_status, f"Ready — hold {self.cfg['hotkey']}")

    # --- dictation flow -----------------------------------------------------
    def _transcribe(self, clip, initial_prompt=None) -> str:
        return transcribe(clip, model=self.cfg["model"], initial_prompt=initial_prompt)

    def _on_press(self) -> None:
        self._ui(self._set_title, REC)
        self._ui(self._set_status, "Recording…")

    def _on_release(self) -> None:
        self._ui(self._set_title, BUSY)
        self._ui(self._set_status, "Transcribing…")

    def _on_text(self, text: str) -> None:
        if text:
            inject.inject_text(
                text,
                method=self.cfg["paste_method"],
                restore_clipboard=self.cfg["restore_clipboard"],
            )
        self._ui(self._set_title, READY)
        self._ui(self._set_status, f"Ready — hold {self.cfg['hotkey']}")

    # --- menu actions -------------------------------------------------------
    def _edit_config(self, _sender) -> None:
        subprocess.Popen(["open", "-t", config.CONFIG_PATH])
        rumps.notification(
            "Voca", "Editing config", "Changes apply after you restart Voca."
        )


if __name__ == "__main__":
    VocaApp().run()
