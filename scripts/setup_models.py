"""One-time model download. Run once (with internet) after installing deps:

    python scripts/setup_models.py

Downloads both on-device models so the app can run fully offline afterwards:
  - mlx-community/whisper-large-v3-turbo  -> Hugging Face cache (used by mlx)
  - felflare/bert-restore-punctuation     -> ./models/ (English punctuation)

The punctuation model is fetched file-by-file from the HF CDN (resolve URLs)
rather than via the metadata API, which is more reliable on flaky networks.
"""

import os
import urllib.request

os.environ["HF_HUB_OFFLINE"] = "0"

WHISPER = "mlx-community/whisper-large-v3-turbo"
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
    os.makedirs(PUNCT_DIR, exist_ok=True)
    base = f"https://huggingface.co/{PUNCT_REPO}/resolve/main"
    for name in PUNCT_FILES:
        dest = os.path.join(PUNCT_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  {name}: already present")
            continue
        print(f"  downloading {name} ...")
        urllib.request.urlretrieve(f"{base}/{name}", dest)
    print(f"Punctuation model ready in {PUNCT_DIR}")


def _download_whisper() -> None:
    from huggingface_hub import snapshot_download

    print(f"Downloading {WHISPER} ...")
    snapshot_download(WHISPER)
    print("Whisper model cached.")


def main() -> int:
    print("Punctuation model (felflare/bert-restore-punctuation):")
    _download_punctuation()
    print()
    _download_whisper()
    print("\nDone. Models ready; the app can run offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
