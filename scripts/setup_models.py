"""One-time model download. Run once (with internet) after installing deps:

    python scripts/setup_models.py

Downloads the on-device models so the app can run fully offline afterwards:
  - mlx-community/whisper-large-v3-turbo   -> Hugging Face cache (used by mlx)
  - felflare/bert-restore-punctuation      -> ./models/ (English punctuation)
  - mlx-community/Qwen2.5-3B-Instruct-4bit -> HF cache (AI cleanup, ~1.8 GB)

The punctuation model is fetched file-by-file from the HF CDN (resolve URLs)
rather than via the metadata API, which is more reliable on flaky networks.
"""

import os

os.environ["HF_HUB_OFFLINE"] = "0"
# Xet-accelerated downloads when hf_xet is installed (harmless if not).
try:
    import hf_xet  # noqa: F401

    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
except Exception:
    pass

WHISPER = "mlx-community/whisper-large-v3-turbo"
CLEANUP_LLM = "mlx-community/Qwen2.5-3B-Instruct-4bit"
PUNCT_REPO = "felflare/bert-restore-punctuation"
PUNCT_FILES = [
    "config.json",
    "vocab.txt",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "pytorch_model.bin",
]
PUNCT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models",
                         "bert-restore-punctuation")


def _download_punctuation() -> None:
    from huggingface_hub import snapshot_download

    os.makedirs(PUNCT_DIR, exist_ok=True)
    snapshot_download(PUNCT_REPO, local_dir=PUNCT_DIR, allow_patterns=PUNCT_FILES)
    print(f"Punctuation model ready in {PUNCT_DIR}")


def _download_whisper() -> None:
    from huggingface_hub import snapshot_download

    print(f"Downloading {WHISPER} ...")
    snapshot_download(WHISPER)
    print("Whisper model cached.")


def _download_cleanup_llm() -> None:
    from huggingface_hub import snapshot_download

    print(f"Downloading {CLEANUP_LLM} (AI cleanup, ~1.8 GB) ...")
    snapshot_download(CLEANUP_LLM)
    print("AI cleanup model cached.")


def main() -> int:
    print("Punctuation model (felflare/bert-restore-punctuation):")
    _download_punctuation()
    print()
    _download_whisper()
    print()
    _download_cleanup_llm()
    print("\nDone. Models ready; the app can run offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
