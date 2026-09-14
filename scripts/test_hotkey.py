"""Phase 3 test: push-to-talk from anywhere, transcript printed to console.

Hold the hotkey (default Right Option), speak, release. The transcript prints
here. Works while ANY app is focused — that's what needs Accessibility
permission. Press Ctrl+C in this terminal to quit.

Usage:
    python scripts/test_hotkey.py                 # Right Option
    python scripts/test_hotkey.py right_command   # a different key
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio
import hotkey
from transcribe import transcribe, warm_up


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else hotkey.DEFAULT_KEY

    if not hotkey.accessibility_trusted():
        print("=" * 62)
        print("ACCESSIBILITY PERMISSION NEEDED")
        print("This app must observe a global hotkey, which macOS gates behind")
        print("Accessibility. Grant it, then run this again:")
        print("  System Settings > Privacy & Security > Accessibility")
        print("  Enable the toggle for your terminal (Terminal / iTerm).")
        print("=" * 62)
        # Keep going anyway: on first run macOS may show the prompt now.

    print(f"Loading model (warming up)...")
    warm_up()

    rec = audio.Recorder()

    def on_press():
        print("\n[recording] hold and speak...", end="", flush=True)

    def on_release():
        print(" released, transcribing...", end="", flush=True)

    def on_text(text: str):
        print(f"\n>>> {text!r}\n")
        print(f"Ready. Hold {key.replace('_', ' ')} to dictate. Ctrl+C to quit.")

    ptt = hotkey.PushToTalk(
        recorder=rec,
        transcribe_fn=transcribe,
        on_text=on_text,
        key=key,
        on_press_cb=on_press,
        on_release_cb=on_release,
    )

    print(f"Ready. Hold {key.replace('_', ' ')} to dictate. Ctrl+C to quit.")
    try:
        ptt.run_forever()
    except KeyboardInterrupt:
        pass
    print("\nBye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
