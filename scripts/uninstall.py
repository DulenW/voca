"""Uninstall the Voca LaunchAgent (stops it and removes login start).

    python scripts/uninstall.py
"""

import os
import subprocess

LABEL = "com.dulenw.voca"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def main() -> int:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
        print(f"Removed {PLIST}")
    print("Voca stopped and removed from login. (Models and settings are kept.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
