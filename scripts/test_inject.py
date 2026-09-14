"""Phase 4 test: dictate and auto-paste into the focused field.

Default (end-to-end): hold the hotkey, speak, release — the transcript is
pasted into whatever app is focused (TextEdit, browser, Slack, ...).

    python scripts/test_inject.py

Isolation mode: skip transcription, just paste a fixed string after a 3s
countdown so you can click into a field. Proves the paste mechanism alone.

    python scripts/test_inject.py --clip "hello from voca"
    python scripts/test_inject.py --clip "typed out" --type
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio
import hotkey
import inject
from transcribe import transcribe, warm_up


def clip_mode(text: str, method: str) -> int:
    print(f"Focus a text field now. Pasting in 3s (method={method})...")
    for n in (3, 2, 1):
        print(f"  {n}", end="\r", flush=True)
        time.sleep(1)
    inject.inject_text(text, method=method)
    print("Done. Check the focused field.")
    return 0


def dictate_mode(key: str) -> int:
    if not hotkey.accessibility_trusted():
        print("Accessibility permission needed (System Settings > Privacy & "
              "Security > Accessibility). See Phase 3 notes.")

    print("Loading model (warming up)...")
    warm_up()

    rec = audio.Recorder()

    def on_press():
        print("\n[recording] speak...", end="", flush=True)

    def on_release():
        print(" transcribing + pasting...", end="", flush=True)

    def on_text(text: str):
        print(f"\n>>> {text!r}")
        inject.inject_text(text)  # paste into whatever is focused
        print(f"Ready. Focus a field, hold {key.replace('_', ' ')}, speak. Ctrl+C to quit.")

    ptt = hotkey.PushToTalk(
        recorder=rec,
        transcribe_fn=transcribe,
        on_text=on_text,
        key=key,
        on_press_cb=on_press,
        on_release_cb=on_release,
    )
    print(f"Ready. Focus a field, hold {key.replace('_', ' ')}, speak. Ctrl+C to quit.")
    try:
        ptt.run_forever()
    except KeyboardInterrupt:
        pass
    print("\nBye.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--clip" in args:
        i = args.index("--clip")
        text = args[i + 1] if i + 1 < len(args) else "hello from voca"
        method = "type" if "--type" in args else "paste"
        return clip_mode(text, method)
    key = next((a for a in args if not a.startswith("--")), hotkey.DEFAULT_KEY)
    return dictate_mode(key)


if __name__ == "__main__":
    raise SystemExit(main())
