"""uninstall.py — remove everything Voca installed.

Dragging an app to the Trash runs no code, so this powers the in-app
"Uninstall Voca…" menu item.

Storage reality: huggingface_hub keeps models in a shared, deduplicated blob
store, and each per-repo folder is just symlinks into it — so trashing a repo
folder frees nothing. We therefore:
  - delete the model repos with huggingface_hub's own cache API, which removes
    only the blobs unique to them and reclaims the space correctly (permanent —
    the models are re-downloadable), and
  - move the rest (the Voca support folder, the login agent, and the app bundle)
    to the Trash, so your settings/vocab and the app stay recoverable until you
    empty it.

No admin/sudo — every target is user-owned. Surgical: only Voca's own model
repos and folders, never a shared parent or another app's models.
"""

from __future__ import annotations

import os

import firstrun
from config import APP_DIR

LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/com.dulenw.voca.plist")
BUNDLE_ID = "com.dulenw.voca"
_DEFAULT_CLEANUP_REPO = "mlx-community/Qwen2.5-3B-Instruct-4bit"


def _cleanup_repo() -> str:
    try:
        import config

        return config.load().get("cleanup_model_local") or _DEFAULT_CLEANUP_REPO
    except Exception:
        return _DEFAULT_CLEANUP_REPO


def model_repos() -> list[str]:
    """The Hugging Face repo ids Voca downloaded (speech + AI cleanup)."""
    return [firstrun.WHISPER, _cleanup_repo()]


def app_bundle_path() -> str | None:
    """Path to the running Voca.app, or None when not running as the Voca bundle.
    From source, mainBundle() is the Python framework's app — we check the bundle
    IDENTIFIER so we can never trash that (or any other) app."""
    try:
        from Foundation import NSBundle

        b = NSBundle.mainBundle()
        if b is None or b.bundleIdentifier() != BUNDLE_ID:
            return None
        p = b.bundlePath()
        return p if p and p.endswith(".app") else None
    except Exception:
        return None


def trash_targets() -> list[str]:
    """Existing non-model paths to move to the Trash (reversible)."""
    out: list[str] = []
    for p in (APP_DIR, LAUNCH_AGENT, app_bundle_path()):
        if p and os.path.exists(p) and p not in out:
            out.append(p)
    return out


def _hf_delete_strategy():
    """(strategy, freed_bytes) for deleting Voca's model revisions from the HF
    cache, or (None, 0) when the cache/API is unavailable."""
    try:
        from huggingface_hub import scan_cache_dir

        info = scan_cache_dir()
        wanted = set(model_repos())
        revisions = [
            rev.commit_hash
            for repo in info.repos if repo.repo_id in wanted
            for rev in repo.revisions
        ]
        if not revisions:
            return None, 0
        strategy = info.delete_revisions(*revisions)
        return strategy, int(strategy.expected_freed_size)
    except Exception as exc:
        print(f"[uninstall] HF cache scan failed: {exc}")
        return None, 0


def _path_size(path: str) -> int:
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.islink(fp):
                continue
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def freed_bytes() -> int:
    """Total space uninstalling will free: the model blobs plus the trashed Voca
    data (the app is freed once the Trash is emptied)."""
    _strategy, model_bytes = _hf_delete_strategy()
    trash_bytes = sum(_path_size(p) for p in trash_targets())
    return model_bytes + trash_bytes


def _move_to_trash(paths: list[str]) -> list[str]:
    """Move each path to the macOS Trash; returns any that couldn't be moved."""
    try:
        from Foundation import NSURL, NSFileManager
    except Exception as exc:
        print(f"[uninstall] Foundation unavailable: {exc}")
        return list(paths)

    fm = NSFileManager.defaultManager()
    failed: list[str] = []
    for p in paths:
        try:
            ok, _resulting, err = fm.trashItemAtURL_resultingItemURL_error_(
                NSURL.fileURLWithPath_(p), None, None
            )
            if not ok:
                print(f"[uninstall] could not trash {p}: {err}")
                failed.append(p)
        except Exception as exc:
            print(f"[uninstall] error trashing {p}: {exc}")
            failed.append(p)
    return failed


def run() -> list[str]:
    """Delete the models (permanent, dedup-aware) and move the rest to the Trash.
    Returns any paths that couldn't be trashed (best-effort)."""
    strategy, _ = _hf_delete_strategy()
    if strategy is not None:
        try:
            strategy.execute()
        except Exception as exc:
            print(f"[uninstall] model delete failed: {exc}")
    return _move_to_trash(trash_targets())
