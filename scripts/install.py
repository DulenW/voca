"""Install Voca as a macOS LaunchAgent — starts now and at every login.

    python scripts/install.py

Why a LaunchAgent instead of a .app bundle: a thin-launcher .app has to exec
an external Python, and the window server won't draw a menu bar status item for
a process launched that way. launchd runs the venv Python directly in your GUI
session (exactly like running it from Terminal, which works), so the menu bar
icon shows reliably — and it auto-starts at login.

Uninstall with: python scripts/uninstall.py
"""

import os
import subprocess
import time

LABEL = "com.dulenw.voca"
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(PROJECT, ".venv", "bin", "python")
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
LOG = os.path.expanduser("~/Library/Logs/Voca.log")

PLIST_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{VENV_PY}</string>
    <string>{os.path.join(PROJECT, "main.py")}</string>
  </array>
  <key>WorkingDirectory</key><string>{PROJECT}</string>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>{LOG}</string>
  <key>StandardErrorPath</key><string>{LOG}</string>
</dict>
</plist>
"""


def main() -> int:
    if not os.path.exists(VENV_PY):
        print(f"ERROR: venv Python not found at {VENV_PY}")
        print("Create it first: python3.12 -m venv .venv && "
              "source .venv/bin/activate && pip install -r requirements.txt")
        return 1

    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w") as f:
        f.write(PLIST_XML)
    print(f"Wrote {PLIST}")

    uid = os.getuid()
    # Reload cleanly if already installed. bootout is asynchronous, so wait for
    # the label to actually disappear before bootstrapping (else bootstrap can
    # fail with an I/O error while the old instance is still unloading).
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True)
    for _ in range(50):  # up to ~5s
        gone = subprocess.run(["launchctl", "print", f"gui/{uid}/{LABEL}"],
                              capture_output=True).returncode != 0
        if gone:
            break
        time.sleep(0.1)

    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", PLIST],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"launchctl bootstrap failed: {r.stderr.strip()}")
        return 1

    print("Voca is installed and running (menu bar: 'Voca…' → 'Voca').")
    print("It will start automatically at login.")
    print(f"Logs: {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
