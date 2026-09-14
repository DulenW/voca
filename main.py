"""main.py — the Voca menu bar app. Wires everything together.

Loads the Whisper model once at startup and keeps it warm for the whole
session. A native CGEventTap (passive at idle, no polling) drives push-to-talk;
on release the audio is transcribed, corrections are applied, and the text is
pasted into the focused app. Custom vocab biases the model's spelling.

Menu bar status:  …=loading  🎙️=ready  🔴=recording  ⏳=transcribing  ⚠️=error

Run:  python main.py   (quit from the menu, or Ctrl+C in the terminal)
"""

from __future__ import annotations

import subprocess
import threading

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from PyObjCTools import AppHelper

import audio
import config
import corrections
import formatting
import hotkey
import inject
import punctuate
from transcribe import transcribe, warm_up

# Menu bar title per state (emoji). These render fine now that the app launches
# via the LaunchAgent in the GUI session; the earlier invisibility was the .app
# launch method hiding the whole item, not the emoji itself.
LOADING, READY, REC, BUSY, ERROR = "…", "🎙️", "🔴", "⏳", "⚠️"


class VocaApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Voca", title=LOADING, quit_button="Quit Voca")
        # Menu-bar-only, no Dock icon. The thin launcher execs an external
        # python, so the bundle's LSUIElement is ignored — set the activation
        # policy in code (Accessory == LSUIElement behavior).
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        self.cfg = config.load()
        corrections.init_db()
        self.recorder = audio.Recorder()
        self._ptt: hotkey.PushToTalk | None = None

        self.status_item = rumps.MenuItem("Loading model…")
        self.vocab_menu = rumps.MenuItem("Vocabulary")
        self.corr_menu = rumps.MenuItem("Corrections")
        self.menu = [
            self.status_item,
            None,  # separator
            rumps.MenuItem("Add Vocab Term…", callback=self._add_vocab),
            rumps.MenuItem("Add Correction…", callback=self._add_correction),
            self.vocab_menu,
            self.corr_menu,
            None,
            rumps.MenuItem("Edit Config…", callback=self._edit_config),
        ]
        self._rebuild_learning_menus()

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
    # Heavy model loading runs on a background thread; the CGEventTap and all
    # keyboard injection run on the main thread (the tap attaches to the main
    # run loop, and macOS input-source calls must be main-thread).
    def _startup(self) -> None:
        try:
            warm_up(self.cfg["model"])
        except Exception as exc:
            self._ui(self._set_title, ERROR)
            self._ui(self._set_status, f"Model failed to load: {exc}")
            return

        # Punctuation model is optional: warm it if present, else degrade to
        # Whisper's own punctuation (restore() becomes a no-op).
        try:
            punctuate.warm_up()
        except Exception as exc:
            print(f"[main] punctuation model not loaded: {exc}")

        # Start the hotkey listener on the main thread.
        self._ui(self._activate)

    def _activate(self) -> None:
        """Main thread: start the event tap on the main run loop and go ready."""
        if not hotkey.accessibility_trusted():
            self._set_title(ERROR)
            self._set_status("Grant Accessibility (System Settings) then restart")
            return

        try:
            # Construction validates the configured hotkey, so keep it inside
            # the guard — a bad `hotkey` in the config raises here.
            self._ptt = hotkey.PushToTalk(
                recorder=self.recorder,
                transcribe_fn=self._transcribe,
                on_text=self._on_text,
                key=self.cfg["hotkey"],
                initial_prompt_provider=corrections.vocab_prompt,
                on_press_cb=self._on_press,
                on_release_cb=self._on_release,
            )
            self._ptt.start()
        except Exception as exc:
            self._set_title(ERROR)
            self._set_status(f"Hotkey failed: {exc}")
            return

        self._set_title(READY)
        self._set_status(f"Ready — hold {self.cfg['hotkey']}")

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
        """Runs on a worker thread. Do the heavy text work here, then hand the
        caret read + keyboard injection to the main thread."""
        if not text:
            self._ui(self._set_title, READY)
            self._ui(self._set_status, f"Ready — hold {self.cfg['hotkey']}")
            return
        text = corrections.apply_corrections(text)  # learned fixes
        text = punctuate.restore(text)  # commas / periods / question marks
        self._ui(self._deliver, text)

    def _deliver(self, text: str) -> None:
        """Main thread: read caret context, format, and paste."""
        before, known = inject.caret_context()  # what's before the cursor
        text = formatting.format_text(
            text,
            before=before,
            context_known=known,
            vocab_terms=[r["term"] for r in corrections.list_vocab()],
        )
        inject.inject_text(
            text,
            method=self.cfg["paste_method"],
            restore_clipboard=self.cfg["restore_clipboard"],
        )
        self._set_title(READY)
        self._set_status(f"Ready — hold {self.cfg['hotkey']}")

    # --- learning-layer menus ----------------------------------------------
    @staticmethod
    def _safe_clear(menu_item: rumps.MenuItem) -> None:
        """Clear a submenu's children. rumps only creates the submenu's backing
        NSMenu on the first add(), so a never-populated submenu has _menu=None
        and clear() would raise — skip it in that case."""
        if getattr(menu_item, "_menu", None) is not None:
            menu_item.clear()

    def _rebuild_learning_menus(self) -> None:
        """Repopulate the Vocabulary and Corrections submenus from the DB.
        Each entry is clickable to delete it."""
        self._safe_clear(self.vocab_menu)
        vocab = corrections.list_vocab()
        if not vocab:
            self.vocab_menu.add(rumps.MenuItem("(none yet)"))
        else:
            for r in vocab:
                self.vocab_menu.add(
                    rumps.MenuItem(
                        r["term"], callback=self._make_delete_vocab(r["id"], r["term"])
                    )
                )

        self._safe_clear(self.corr_menu)
        corrs = corrections.list_corrections()
        if not corrs:
            self.corr_menu.add(rumps.MenuItem("(none yet)"))
        else:
            for r in corrs:
                label = (
                    f"{r['wrong_text']} → {r['correct_text']}  (×{r['hit_count']})"
                )
                self.corr_menu.add(
                    rumps.MenuItem(
                        label, callback=self._make_delete_correction(r["id"], label)
                    )
                )

    def _add_vocab(self, _sender) -> None:
        resp = rumps.Window(
            message="Word / name / term to spell correctly:",
            title="Add Vocab Term",
            dimensions=(320, 24),
        ).run()
        if resp.clicked and resp.text.strip():
            if corrections.add_vocab(resp.text):
                self._rebuild_learning_menus()
            else:
                rumps.alert("Voca", "That term is empty or already in your vocab.")

    def _add_correction(self, _sender) -> None:
        wrong = rumps.Window(
            message="Wrong text (what it hears):",
            title="Add Correction — 1 of 2",
            dimensions=(320, 24),
        ).run()
        if not (wrong.clicked and wrong.text.strip()):
            return
        correct = rumps.Window(
            message=f"Correct text for “{wrong.text.strip()}”:",
            title="Add Correction — 2 of 2",
            dimensions=(320, 24),
        ).run()
        if not (correct.clicked and correct.text.strip()):
            return
        corrections.add_correction(wrong.text, correct.text)
        self._rebuild_learning_menus()

    def _make_delete_vocab(self, vocab_id: int, term: str):
        def cb(_sender) -> None:
            if rumps.alert(
                title="Delete vocab term?", message=term, ok="Delete", cancel="Cancel"
            ):
                corrections.delete_vocab(vocab_id)
                self._rebuild_learning_menus()

        return cb

    def _make_delete_correction(self, correction_id: int, label: str):
        def cb(_sender) -> None:
            if rumps.alert(
                title="Delete correction?", message=label, ok="Delete", cancel="Cancel"
            ):
                corrections.delete_correction(correction_id)
                self._rebuild_learning_menus()

        return cb

    # --- menu actions -------------------------------------------------------
    def _edit_config(self, _sender) -> None:
        subprocess.Popen(["open", "-t", config.CONFIG_PATH])
        # A banner needs an app bundle, which the LaunchAgent isn't, so it may
        # not show on modern macOS — guard it and never let it break the click.
        try:
            rumps.notification(
                "Voca", "Editing config",
                "Reload to apply: python scripts/install.py (or quit + login)."
            )
        except Exception:
            pass


if __name__ == "__main__":
    VocaApp().run()
