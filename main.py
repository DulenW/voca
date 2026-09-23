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

import firstrun

# Set Hugging Face offline mode from model presence BEFORE importing the ML
# libraries below — transcribe/punctuate read HF_HUB_OFFLINE at import time.
firstrun.configure_env()

# Import torch on the MAIN thread, once, before any background thread can.
# torch's C++ dispatcher init (libtorch, c10::parseDispatchKey) is NOT safe to
# trigger from a worker thread while mlx is also initializing Metal — doing so
# segfaults intermittently (SIGSEGV in initDispatchBindings during `import
# torch`). The punctuation model and VAD both import torch lazily on the
# startup thread, so we force its one-time init here first; those later imports
# then just hit the module cache. Guarded so a torch-less setup still runs.
try:
    import torch  # noqa: F401
except Exception as exc:
    print(f"[main] torch preload skipped: {exc}")

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from Foundation import NSBundle
from PyObjCTools import AppHelper

import audio
import config
import corrections
import enhance
import formatting
import hotkey
import inject
import punctuate
import speech
from transcribe import transcribe, warm_up

# Menu bar title per state (emoji). These render fine now that the app launches
# via the LaunchAgent in the GUI session; the earlier invisibility was the .app
# launch method hiding the whole item, not the emoji itself.
LOADING, READY, REC, BUSY, ERROR, DOWNLOADING = "…", "🎙️", "🔴", "⏳", "⚠️", "⬇"


def _app_bundle_path() -> str | None:
    """Path to the running Voca.app bundle, or None when run from source."""
    path = NSBundle.mainBundle().bundlePath()
    return path if path and path.endswith(".app") else None


def _login_item_present() -> bool:
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get the name of every login item'],
            capture_output=True, text=True, timeout=5,
        )
        return "Voca" in out.stdout
    except Exception:
        return False


def _set_login_item(enable: bool) -> None:
    if enable:
        app = _app_bundle_path()
        if not app:
            raise RuntimeError("Start at Login needs the installed Voca.app.")
        script = (
            'tell application "System Events" to make login item at end '
            f'with properties {{path:"{app}", hidden:false}}'
        )
    else:
        script = 'tell application "System Events" to delete login item "Voca"'
    subprocess.run(["osascript", "-e", script], check=True, timeout=5)


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
            rumps.MenuItem("Start at Login", callback=self._toggle_login_item),
        ]
        self._rebuild_learning_menus()
        self.menu["Start at Login"].state = _login_item_present()

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
        # First launch: download the models (with progress in the menu bar).
        if not firstrun.models_present():
            self._ui(self._set_title, DOWNLOADING)
            try:
                firstrun.ensure_models(
                    lambda msg: self._ui(self._set_status, msg)
                )
            except Exception as exc:
                self._ui(self._set_title, ERROR)
                self._ui(self._set_status, f"Model download failed: {exc}")
                return

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

        # Warm the speech-gate VAD (silences Whisper's hallucinations).
        try:
            speech.warm_up()
        except Exception as exc:
            print(f"[main] VAD not loaded: {exc}")

        # Warm the AI cleanup model (no-op unless the local backend is on) so the
        # first dictation isn't slowed by a cold model load.
        try:
            enhance.warm_up(self.cfg)
        except Exception as exc:
            print(f"[main] cleanup model not loaded: {exc}")

        # Start the hotkey listener on the main thread.
        self._ui(self._activate)

    def _activate(self) -> None:
        """Main thread: start the event tap on the main run loop and go ready."""
        if not hotkey.accessibility_trusted():
            # Pop the system prompt (adds Voca to the Accessibility list); the
            # user enables it, then reopens Voca.
            hotkey.request_accessibility()
            self._set_title(ERROR)
            self._set_status("Enable Voca under Accessibility, then reopen Voca")
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
                on_idle_cb=self._on_idle,
                mute_system_audio=self.cfg["mute_system_audio"],
                streaming=self.cfg["streaming"],
            )
            self._ptt.start()
        except Exception as exc:
            self._set_title(ERROR)
            self._set_status(f"Hotkey failed: {exc}")
            return

        self._set_title(READY)
        self._set_status(f"Ready — hold {self.cfg['hotkey']}")

    # --- dictation flow -----------------------------------------------------
    def _transcribe(self, clip, initial_prompt=None, prev_text=None) -> str:
        return transcribe(
            clip,
            model=self.cfg["model"],
            initial_prompt=initial_prompt,
            prev_text=prev_text,
        )

    def _on_press(self) -> None:
        self._ui(self._set_title, REC)
        self._ui(self._set_status, "Recording…")

    def _on_release(self) -> None:
        self._ui(self._set_title, BUSY)
        self._ui(self._set_status, "Transcribing…")

    def _on_text(self, text: str) -> None:
        """Deliver one transcript (a whole clip in batch mode, or one phrase in
        chunked mode) into the focused app. Runs entirely on a worker thread —
        corrections, punctuation, caret read, and paste. Nothing here touches
        the main run loop, so the app never freezes even if the caret read
        (Accessibility) or paste stalls on an unresponsive target app.
        Injection uses thread-safe Quartz events, so it's safe off-main.

        In chunked mode the caret read sees the previous phrase already pasted,
        so cross-phrase spacing and capitalization fall out for free."""
        if not text:
            return
        text = corrections.apply_corrections(text)  # learned fixes
        vocab_terms = [r["term"] for r in corrections.list_vocab()]
        if self.cfg["cleanup_backend"] != "off":
            # AI cleanup handles punctuation, grammar, fillers, and smart
            # formatting in one pass (falls back to raw text on any failure).
            self._ui(self._set_status, "Cleaning up…")
            text = enhance.enhance(text, vocab_terms, self.cfg)
        else:
            text = punctuate.restore(text)  # commas / periods / question marks
        before, known = inject.caret_context()  # what's before the cursor
        text = formatting.format_text(
            text,
            before=before,
            context_known=known,
            vocab_terms=vocab_terms,
        )
        inject.inject_text(
            text,
            method=self.cfg["paste_method"],
            restore_clipboard=self.cfg["restore_clipboard"],
        )

    def _on_idle(self) -> None:
        """All transcription has drained — back to ready. (Status lives here,
        not in _on_text, so a phrase finishing mid-hold doesn't flip us out of
        the recording state.)"""
        self._ui(self._set_title, READY)
        self._ui(self._set_status, f"Ready — hold {self.cfg['hotkey']}")

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
    def _toggle_login_item(self, sender) -> None:
        try:
            _set_login_item(not sender.state)
            sender.state = not sender.state
        except Exception as exc:
            rumps.alert("Voca", f"Couldn't change login item:\n{exc}")

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
