"""firstrun.py — provision Voca's models under the app-support dir.

Models download once into ~/Library/Application Support/Voca/models/<name>/ as
real files, so uninstalling (which trashes that dir) reclaims the space, and so
we control the source and can make downloads resumable.

Source of truth is MODELS_BASE_URL (a Cloudflare R2 public base) with resumable
HTTP downloads; if it's unset or unreachable, we fall back to Hugging Face
(huggingface_hub). Models already sitting in the HF cache from an older install
are reused as-is (no re-download).

Whisper is fetched first (ensure_whisper) so the app is usable for dictation
while the larger AI-cleanup model finishes in the background (ensure_cleanup).

main.py calls configure_env() at the very top, then the ensure_* calls during
startup.
"""

from __future__ import annotations

import os
import subprocess
import time

APP_SUPPORT = os.path.expanduser("~/Library/Application Support/Voca")
MODELS_DIR = os.path.join(APP_SUPPORT, "models")
_HF_HUB = os.path.expanduser("~/.cache/huggingface/hub")

# Public base URL of the Cloudflare R2 bucket hosting the models (NO trailing
# slash), e.g. "https://pub-xxxx.r2.dev". Empty => download from Hugging Face.
# Files are expected at {MODELS_BASE_URL}/{folder}/{filename}.
MODELS_BASE_URL = ""

WHISPER = "mlx-community/whisper-large-v3-turbo"
_DEFAULT_CLEANUP = "mlx-community/Qwen2.5-3B-Instruct-4bit"

# Exact files per model folder (folder == R2 prefix == local subdir == the HF
# repo basename under mlx-community/). README/.gitattributes are excluded.
MODEL_MANIFEST = {
    "whisper-large-v3-turbo": [
        "config.json",
        "weights.safetensors",
    ],
    "Qwen2.5-3B-Instruct-4bit": [
        "config.json",
        "model.safetensors",
        "model.safetensors.index.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "merges.txt",
        "vocab.json",
    ],
}
# The file whose presence means a model finished downloading (the big weights).
_KEY_FILE = {
    "whisper-large-v3-turbo": "weights.safetensors",
    "Qwen2.5-3B-Instruct-4bit": "model.safetensors",
}

# Punctuation model — only used when AI cleanup is off. Stays on Hugging Face.
PUNCT_DIR = os.path.join(MODELS_DIR, "bert-restore-punctuation")
_REPO_PUNCT_DIR = os.path.join(
    os.path.dirname(__file__), "models", "bert-restore-punctuation"
)
PUNCT_REPO = "felflare/bert-restore-punctuation"
PUNCT_FILES = [
    "config.json", "vocab.txt", "tokenizer_config.json",
    "special_tokens_map.json", "pytorch_model.bin",
]


# --- config helpers --------------------------------------------------------
def _cfg() -> dict:
    try:
        import config

        return config.load()
    except Exception:
        return {}


def _whisper_repo() -> str:
    return _cfg().get("model") or WHISPER


def _cleanup_local_repo() -> str | None:
    """The on-device cleanup model to ensure, or None when local cleanup is off."""
    cfg = _cfg()
    if cfg.get("cleanup_backend") == "local":
        return cfg.get("cleanup_model_local") or _DEFAULT_CLEANUP
    return None


def _punct_needed() -> bool:
    return _cfg().get("cleanup_backend") == "off"


def _base_url() -> str:
    """R2 base URL: a config override wins over the baked-in constant (lets you
    point at a bucket for testing without rebuilding)."""
    return (_cfg().get("models_base_url") or MODELS_BASE_URL).rstrip("/")


# --- model paths / presence ------------------------------------------------
def _folder(model_id: str) -> str:
    return model_id.rsplit("/", 1)[-1]


def local_model_dir(model_id: str) -> str:
    return os.path.join(MODELS_DIR, _folder(model_id))


def _hf_cache_dir(model_id: str) -> str | None:
    """A ready snapshot dir for this repo in the HF cache (older installs), else
    None. Lets an upgrading user reuse already-downloaded models."""
    d = os.path.join(_HF_HUB, "models--" + model_id.replace("/", "--"), "snapshots")
    if not os.path.isdir(d):
        return None
    for s in os.listdir(d):
        snap = os.path.join(d, s)
        if os.path.exists(os.path.join(snap, "config.json")):
            return snap
    return None


def _local_present(model_id: str) -> bool:
    """True if the model's key file exists in our app-support dir (completed)."""
    key = _KEY_FILE.get(_folder(model_id))
    d = local_model_dir(model_id)
    if key:
        p = os.path.join(d, key)
        return os.path.exists(p) and os.path.getsize(p) > 0
    return os.path.isdir(d) and any(
        f.endswith(".safetensors") for f in os.listdir(d)
    )


def _model_present(model_id: str) -> bool:
    return _local_present(model_id) or _hf_cache_dir(model_id) is not None


def resolved_model_path(model_id: str) -> str:
    """Where mlx should load the model from: our local dir if downloaded there,
    else a ready HF-cache snapshot, else the repo id (so mlx fetches from HF)."""
    if _local_present(model_id):
        return local_model_dir(model_id)
    hf = _hf_cache_dir(model_id)
    return hf if hf else model_id


def whisper_present() -> bool:
    return _model_present(_whisper_repo())


def cleanup_present() -> bool:
    repo = _cleanup_local_repo()
    return repo is None or _model_present(repo)


def punct_present() -> bool:
    for d in (PUNCT_DIR, _REPO_PUNCT_DIR):
        w = os.path.join(d, "pytorch_model.bin")
        if os.path.exists(w) and os.path.getsize(w) > 0:
            return True
    return False


def models_present() -> bool:
    if not whisper_present() or not cleanup_present():
        return False
    if _punct_needed() and not punct_present():
        return False
    return True


# --- env -------------------------------------------------------------------
def configure_env() -> None:
    """Set HF offline based on model presence (offline once everything is cached;
    online on first run for the HF fallback). Also enable Xet high-performance
    downloads when hf_xet is available. Guarded."""
    os.environ["HF_HUB_OFFLINE"] = "1" if models_present() else "0"
    try:
        import hf_xet  # noqa: F401

        os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    except Exception:
        pass


# --- download --------------------------------------------------------------
_UA = "Voca/1.0"


def _remote_size(url: str) -> int | None:
    """Total size from a HEAD request, or None if unknown."""
    try:
        out = subprocess.run(
            ["curl", "-sIL", "-A", _UA, url],
            capture_output=True, text=True, timeout=30,
        ).stdout
        size = None
        for line in out.splitlines():
            if line.lower().startswith("content-length:"):
                size = int(line.split(":", 1)[1].strip())
        return size
    except Exception:
        return None


def _download_file(url: str, dest: str, label: str, progress) -> None:
    """Resumable download of one file via curl (universally available on macOS,
    works in and out of the app bundle). Downloads to dest.part — curl's `-C -`
    resumes from its current size — and renames to dest when complete. The .part
    persists across app restarts, so a dropped connection continues. Retries
    with backoff. Progress is polled from the growing file when the size is
    known."""
    part = dest + ".part"
    total = _remote_size(url)
    for attempt in range(6):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if total and have >= total:
            os.replace(part, dest)
            return
        cmd = ["curl", "-sL", "--fail", "-A", _UA, "-o", part, url]
        if total:  # resume only when we can verify completion by size
            cmd[2:2] = ["-C", "-"]
        else:      # unknown size → fresh download to avoid a bad resume
            if os.path.exists(part):
                os.remove(part)
        proc = subprocess.Popen(cmd)
        while proc.poll() is None:
            time.sleep(0.5)
            if total and os.path.exists(part):
                pct = min(100, 100 * os.path.getsize(part) // total)
                progress(f"{label} {pct}%")
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if proc.returncode == 0 and (not total or have >= total):
            os.replace(part, dest)
            return
        print(f"[firstrun] {url} attempt {attempt + 1} rc={proc.returncode} "
              f"({have}/{total})")
        time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"could not download {url}")


def _ensure_model(model_id: str, label: str, progress) -> None:
    """Fully provision one model locally: R2 first (resumable), HF as fallback."""
    if _model_present(model_id):
        return
    folder = _folder(model_id)
    dest_dir = local_model_dir(model_id)
    os.makedirs(dest_dir, exist_ok=True)
    files = MODEL_MANIFEST.get(folder)
    base = _base_url()

    if files:
        # Try each source via curl (IPv4-resilient + resumable): the R2 bucket
        # first (if configured), then Hugging Face's direct file URLs. curl's
        # Happy-Eyeballs falls back to IPv4, so a broken IPv6 route can't hang
        # the download the way huggingface_hub's Python client can.
        sources = []
        if base:
            sources.append((f"{base}/{folder}", "R2"))
        sources.append(
            (f"https://huggingface.co/{model_id}/resolve/main", "Hugging Face")
        )
        for prefix, name_of in sources:
            try:
                for name in files:
                    dest = os.path.join(dest_dir, name)
                    if not os.path.exists(dest):
                        _download_file(f"{prefix}/{name}", dest, label, progress)
                return
            except Exception as exc:
                print(f"[firstrun] {name_of} download failed ({exc}); trying next")

    # Unknown/overridden model with no manifest — let huggingface_hub discover
    # and fetch the file list.
    progress(f"{label} (Hugging Face)…")
    from huggingface_hub import snapshot_download

    snapshot_download(
        model_id, local_dir=dest_dir, allow_patterns=files if files else None
    )


def ensure_whisper(progress) -> None:
    if not whisper_present():
        _ensure_model(_whisper_repo(), "Downloading speech model…", progress)


def ensure_cleanup(progress) -> None:
    repo = _cleanup_local_repo()
    if repo and not _model_present(repo):
        _ensure_model(repo, "Downloading AI cleanup model…", progress)
    if _punct_needed() and not punct_present():
        progress("Downloading punctuation model…")
        os.makedirs(PUNCT_DIR, exist_ok=True)
        from huggingface_hub import snapshot_download

        snapshot_download(PUNCT_REPO, local_dir=PUNCT_DIR, allow_patterns=PUNCT_FILES)


def ensure_models(progress) -> None:
    """Provision everything (whisper first, then cleanup)."""
    ensure_whisper(progress)
    ensure_cleanup(progress)
    progress("Models ready.")
