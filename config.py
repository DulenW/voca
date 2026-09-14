"""config.py — load and save the JSON config in the app support directory.

Config lives at ~/Library/Application Support/Voca/config.json and is created
with defaults on first run. It's plain JSON so it can be hand-edited (the menu
bar app offers "Edit Config…"); changes apply on restart.
"""

from __future__ import annotations

import json
import os

APP_DIR = os.path.expanduser("~/Library/Application Support/Voca")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "hotkey": "right option",  # see hotkey.KEY_MAP for valid values
    "model": "mlx-community/whisper-large-v3-turbo",
    "restore_clipboard": True,  # restore previous clipboard after pasting
    "paste_method": "paste",  # "paste" (Cmd+V) or "type" (keystrokes)
}


def load() -> dict:
    """Return the config, filling any missing keys from DEFAULTS. Creates the
    file on first run and normalizes it back to disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update({k: loaded[k] for k in DEFAULTS if k in loaded})
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] could not read {CONFIG_PATH}: {exc}; using defaults")
    save(cfg)
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
