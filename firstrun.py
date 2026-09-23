"""firstrun.py — download the models on first launch.

The bundled .app is read-only, so the (small) punctuation model lives under the
writable app-support dir; Whisper uses the standard Hugging Face cache. Must run
BEFORE transcribe / punctuate are imported (they pin HF_HUB_OFFLINE), so main.py
calls configure_env() at the very top and ensure_models() during startup.
"""

from __future__ import annotations

import os
import urllib.request

APP_SUPPORT = os.path.expanduser("~/Library/Application Support/Voca")
PUNCT_DIR = os.path.join(APP_SUPPORT, "models", "bert-restore-punctuation")
# Source installs keep the punctuation model in the repo (via setup_models.py).
_REPO_PUNCT_DIR = os.path.join(
    os.path.dirname(__file__), "models", "bert-restore-punctuation"
)

WHISPER = "mlx-community/whisper-large-v3-turbo"
_HF_HUB = os.path.expanduser("~/.cache/huggingface/hub")
_WHISPER_SNAPSHOTS = os.path.join(
    _HF_HUB, "models--mlx-community--whisper-large-v3-turbo", "snapshots"
)

PUNCT_REPO = "felflare/bert-restore-punctuation"
PUNCT_FILES = [
    "config.json",
    "vocab.txt",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "pytorch_model.bin",
]


def _cleanup_local_repo() -> str | None:
    """The on-device AI-cleanup model to ensure, or None when local cleanup is
    off (backend "off"/"cloud"). Read from config so we only download the ~1.8GB
    model for users who actually use local cleanup."""
    try:
        import config

        cfg = config.load()
    except Exception:
        return None
    if cfg.get("cleanup_backend") == "local":
        return cfg.get("cleanup_model_local") or "mlx-community/Qwen2.5-3B-Instruct-4bit"
    return None


def _hf_snapshot_present(repo: str) -> bool:
    """True if a Hugging Face repo is already in the local cache."""
    d = os.path.join(_HF_HUB, "models--" + repo.replace("/", "--"), "snapshots")
    if not os.path.isdir(d):
        return False
    return any(
        os.path.exists(os.path.join(d, s, "config.json")) for s in os.listdir(d)
    )


def whisper_present() -> bool:
    if not os.path.isdir(_WHISPER_SNAPSHOTS):
        return False
    return any(
        os.path.exists(os.path.join(_WHISPER_SNAPSHOTS, s, "config.json"))
        for s in os.listdir(_WHISPER_SNAPSHOTS)
    )


def punct_present() -> bool:
    for d in (PUNCT_DIR, _REPO_PUNCT_DIR):
        weights = os.path.join(d, "pytorch_model.bin")
        if os.path.exists(weights) and os.path.getsize(weights) > 0:
            return True
    return False


def models_present() -> bool:
    if not (whisper_present() and punct_present()):
        return False
    repo = _cleanup_local_repo()
    if repo and not _hf_snapshot_present(repo):
        return False
    return True


def configure_env() -> None:
    """Set HF offline based on model presence. Call at the very top of main.py,
    before importing transcribe/punctuate. Offline once cached (fast, wifi-
    independent); online on first run so the download can happen."""
    os.environ["HF_HUB_OFFLINE"] = "1" if models_present() else "0"


def ensure_models(progress) -> None:
    """Download any missing model, reporting coarse progress via progress(str).
    No-op when both are already present."""
    if models_present():
        return

    if not punct_present():
        os.makedirs(PUNCT_DIR, exist_ok=True)
        base = f"https://huggingface.co/{PUNCT_REPO}/resolve/main"
        for i, name in enumerate(PUNCT_FILES, 1):
            dest = os.path.join(PUNCT_DIR, name)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                continue
            progress(f"Downloading punctuation model… ({i}/{len(PUNCT_FILES)})")
            urllib.request.urlretrieve(f"{base}/{name}", dest)

    if not whisper_present():
        progress("Downloading speech model… (~1.5 GB, one time)")
        from huggingface_hub import snapshot_download

        snapshot_download(WHISPER)

    repo = _cleanup_local_repo()
    if repo and not _hf_snapshot_present(repo):
        progress("Downloading AI cleanup model… (~1.8 GB, one time)")
        from huggingface_hub import snapshot_download

        snapshot_download(repo)

    progress("Models ready.")
