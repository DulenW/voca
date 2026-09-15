"""punctuate.py — restore punctuation with a local English model.

Uses felflare/bert-restore-punctuation to decide where periods, commas, and
question marks belong. To keep the custom-vocab capitalization (e.g. proper
names) intact, we feed the model lowercased words to locate punctuation, but
reapply those marks onto Whisper's ORIGINAL words — the model's own
truecasing is ignored so it never down-cases a name it doesn't know.

Loads from the local HF cache (offline, like the STT model). If the model
isn't available it degrades to a no-op so the app never breaks. Runs only
during a dictation, never at idle.
"""

from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")

REPO = "felflare/bert-restore-punctuation"
# Where the model may live: the app-support dir (downloaded on first launch by
# firstrun.py) or an in-repo models/ dir (source install via setup_models.py).
# Resolved at load time, not import time, since first-run downloads it later.
_CANDIDATE_DIRS = [
    os.path.expanduser(
        "~/Library/Application Support/Voca/models/bert-restore-punctuation"
    ),
    os.path.join(os.path.dirname(__file__), "models", "bert-restore-punctuation"),
]


def _resolve_model() -> str:
    for d in _CANDIDATE_DIRS:
        if os.path.exists(os.path.join(d, "config.json")):
            return d
    return REPO  # fall back to the HF cache by repo id

# felflare/bert-restore-punctuation ships generic LABEL_0..14 in its config, so
# we map label index -> its real meaning here (rpunct's scheme). Each label is
# [punctuation-to-append][case]: char 0 is the mark after the word (O=none),
# char 1 is U=capitalize / O=lowercase. We use only the punctuation and keep
# Whisper's own capitalization.
_LABELS = ["OU", "OO", ".O", "!O", ",O", ".U", "!U", ",U",
           ":O", ";O", ":U", "'O", "-O", "?O", "?U"]

# Marks we allow the model to insert (skip stray apostrophes/hyphens).
_ALLOWED = set(".,?!;:")
# Strip these from Whisper's words to get clean cores; keep ' and - inside words.
_STRIP = ".,!?;:……\"”“"

_tokenizer = None
_model = None
_available = False


def _core(word: str) -> str:
    return word.strip(_STRIP)


def _load() -> bool:
    """Load the model once. Returns False if unavailable (then restore is a
    no-op)."""
    global _tokenizer, _model, _available
    if _model is not None:
        return _available
    try:
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        model_path = _resolve_model()
        _tokenizer = AutoTokenizer.from_pretrained(model_path)
        _model = AutoModelForTokenClassification.from_pretrained(model_path)
        _model.eval()
        _available = True
    except Exception as exc:
        print(f"[punctuate] model unavailable, skipping punctuation: {exc}")
        _model = False  # sentinel so we don't retry every call
        _available = False
    return _available


def warm_up() -> None:
    if _load():
        restore("this is a warm up sentence for the punctuation model")


def restore(text: str) -> str:
    """Return text with punctuation restored, preserving original word casing.
    No-op if the model isn't available or the text is empty."""
    if not text or not text.strip() or not _load():
        return text

    import torch

    raw = text.split()
    cores = [_core(w) for w in raw]
    words = [c for c in cores if c]  # drop tokens that were pure punctuation
    if not words:
        return text

    enc = _tokenizer(
        [w.lower() for w in words],
        is_split_into_words=True,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    )
    with torch.no_grad():
        preds = _model(**enc).logits[0].argmax(-1).tolist()

    # Take the first sub-token's label for each word.
    label_for: dict[int, str] = {}
    for pos, wid in enumerate(enc.word_ids()):
        if wid is None or wid in label_for:
            continue
        pred = preds[pos]
        label_for[wid] = _LABELS[pred] if 0 <= pred < len(_LABELS) else "OO"

    out = []
    for j, w in enumerate(words):
        label = label_for.get(j, "OO")
        mark = label[0] if label[0] in _ALLOWED else ""
        out.append(w + mark)
    return " ".join(out)
