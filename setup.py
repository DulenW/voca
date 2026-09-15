"""py2app build config for Voca.

Build a self-contained Voca.app (embeds Python + all libraries) with:

    python setup.py py2app

Models are NOT bundled — they download on first launch (see firstrun.py), so
the app stays ~1.5 GB. Produces dist/Voca.app.
"""

import os
import sys

from setuptools import setup

# py2app's modulegraph recurses deeply through big packages (torch/sympy) and
# blows the default 1000-frame limit with a RecursionError. Raise it.
sys.setrecursionlimit(10000)

# mlx ships as a PEP 420 namespace package (no __init__.py, just compiled .so),
# which py2app's modulegraph can't analyze ("No module named 'mlx'"). Give it an
# empty __init__.py so it's treated as a regular package. Harmless at runtime.
import mlx  # noqa: E402

_mlx_init = os.path.join(list(mlx.__path__)[0], "__init__.py")
if not os.path.exists(_mlx_init):
    open(_mlx_init, "a").close()

APP = ["main.py"]

# py2app's static analysis misses lazy/native imports in the ML stack, so force
# whole packages in. Native dylibs (torch/lib, mlx metal, portaudio) come along
# with their packages.
PACKAGES = [
    "rumps",
    "mlx",
    "mlx_whisper",
    "transformers",
    "torch",
    "numpy",
    "scipy",
    "numba",
    "llvmlite",
    "sounddevice",
    "_sounddevice_data",  # holds libportaudio.dylib — must stay out of the zip
    "soundfile",
    "_soundfile_data",  # holds libsndfile dylib — must stay out of the zip
    "silero_vad",  # VAD; bundles its model file. torchaudio (its only other
    # dependency) is intentionally NOT bundled — its native lib won't load in a
    # bundle and speech.py stubs it, since we never use torchaudio's file I/O.
    "huggingface_hub",
    "tokenizers",
    "safetensors",
    "sympy",
    "networkx",
    "certifi",
    "regex",
    "tqdm",
    "filelock",
    "pyperclip",
    "yaml",
]

OPTIONS = {
    "plist": {
        "CFBundleName": "Voca",
        "CFBundleDisplayName": "Voca",
        "CFBundleIdentifier": "com.dulenw.voca",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1.1.0",
        "LSUIElement": True,  # menu-bar only, no Dock icon
        "LSMinimumSystemVersion": "13.0",
        "NSMicrophoneUsageDescription":
            "Voca transcribes your speech locally on this Mac.",
    },
    "iconfile": "assets/icon.icns",
    "packages": PACKAGES,
    # These are imported dynamically / via pyobjc and can be missed.
    "includes": ["pkg_resources"],
    "excludes": ["pip", "setuptools", "wheel", "PyInstaller", "torchaudio"],
    # Don't try to byte-compile giant packages semi-standalone; full standalone.
    "optimize": 0,
}

setup(
    app=APP,
    name="Voca",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
