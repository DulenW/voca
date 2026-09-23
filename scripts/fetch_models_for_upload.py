"""fetch_models_for_upload.py — gather the model files to host on Cloudflare R2.

Run once:

    python scripts/fetch_models_for_upload.py

Copies the exact files Voca needs into ./models_upload/<folder>/, ready to drag
into your R2 bucket. It reuses the models already in your local cache (a fast
local copy, no network); only if a model isn't cached does it download it.

Upload the folders keeping their names, so the bucket ends up with e.g.
    <bucket>/whisper-large-v3-turbo/weights.safetensors
    <bucket>/Qwen2.5-3B-Instruct-4bit/model.safetensors
Then enable the bucket's public r2.dev URL and give that base URL to Voca.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import firstrun  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models_upload")


def main() -> int:
    for folder, files in firstrun.MODEL_MANIFEST.items():
        repo = f"mlx-community/{folder}"
        dest = os.path.join(OUT, folder)
        os.makedirs(dest, exist_ok=True)

        # resolved_model_path returns the local cache dir (HF cache / app-support)
        # when the model is present — copy from there with no network.
        src = firstrun.resolved_model_path(repo)
        if os.path.isdir(src):
            print(f"\nCopying {folder} from local cache:\n  {src}")
            missing = []
            for name in files:
                s = os.path.join(src, name)
                if os.path.exists(s):
                    shutil.copy(s, os.path.join(dest, name))  # follows symlinks
                    print(f"  ✓ {name}")
                else:
                    missing.append(name)
            if not missing:
                continue
            print(f"  (missing locally: {', '.join(missing)} — downloading those)")
            _download(repo, dest, missing)
        else:
            print(f"\n{folder} not cached — downloading from Hugging Face…")
            _download(repo, dest, files)

    print(f"\nDone. Upload the folders in:\n  {OUT}\n"
          "to your R2 bucket (keep the folder names), enable the public r2.dev "
          "URL, and give that base URL to Voca.")
    return 0


def _download(repo: str, dest: str, files: list) -> None:
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import snapshot_download

    snapshot_download(repo, local_dir=dest, allow_patterns=files)


if __name__ == "__main__":
    raise SystemExit(main())
