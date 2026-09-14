"""Build Voca.app — a thin launcher bundle for the menu bar app.

    python scripts/build_app.py

Creates ./Voca.app, whose executable runs this repo's venv Python on main.py.
It's a real .app (menu-bar only via LSUIElement) you can double-click, move to
/Applications, or set to launch at login. It does NOT embed Python or the ML
libraries — it points at the repo's .venv, so keep the repo in place.

Re-run this after moving the repo (the launcher hardcodes absolute paths).
"""

import os
import stat
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(PROJECT, ".venv", "bin", "python")
APP = os.path.join(PROJECT, "Voca.app")

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Voca</string>
  <key>CFBundleDisplayName</key><string>Voca</string>
  <key>CFBundleIdentifier</key><string>com.dulenw.voca</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>Voca</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Voca transcribes your speech locally on this Mac.</string>
</dict>
</plist>
"""

LAUNCHER = f"""#!/bin/bash
# Thin launcher: run the Voca menu bar app from the repo's virtualenv.
cd "{PROJECT}" || exit 1
exec "{VENV_PY}" main.py >> "$HOME/Library/Logs/Voca.log" 2>&1
"""


def main() -> int:
    if not os.path.exists(VENV_PY):
        print(f"ERROR: venv Python not found at {VENV_PY}")
        print("Create it first: python3.12 -m venv .venv && "
              "source .venv/bin/activate && pip install -r requirements.txt")
        return 1

    macos_dir = os.path.join(APP, "Contents", "MacOS")
    os.makedirs(macos_dir, exist_ok=True)

    with open(os.path.join(APP, "Contents", "Info.plist"), "w") as f:
        f.write(INFO_PLIST)

    launcher_path = os.path.join(macos_dir, "Voca")
    with open(launcher_path, "w") as f:
        f.write(LAUNCHER)
    os.chmod(launcher_path, os.stat(launcher_path).st_mode | stat.S_IEXEC |
             stat.S_IXGRP | stat.S_IXOTH)

    print(f"Built {APP}")
    print("Double-click it in Finder, or run:  open Voca.app")
    print("Move it to /Applications if you like (it still points at this repo).")
    print("Logs: ~/Library/Logs/Voca.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
