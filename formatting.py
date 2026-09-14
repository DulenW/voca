"""formatting.py — shape a raw transcript to fit where it's being inserted.

Whisper transcribes each push-to-talk clip in isolation, so it always
capitalizes the first word and may omit a final period. This module adapts the
text to context (what's before the caret in the focused field):

  - At a sentence start (empty field, or after . ! ? or a newline): capitalize
    the first word and ensure a terminal mark (. or ?).
  - Mid-sentence: lowercase the first word (unless it's "I" or a known vocab
    proper noun), add a leading space if needed, and DON'T force an end mark.

Platform-independent and pure (easy to unit-test); the macOS caret reading
lives in inject.py.
"""

from __future__ import annotations

_ENDS = ".!?"
_SENTENCE_BOUNDARY = _ENDS + "\n\r:"  # after these, a new sentence begins

# If a standalone utterance starts with one of these, end it with "?" not ".".
_QUESTION_STARTERS = {
    "what", "why", "how", "when", "where", "who", "whose", "whom", "which",
    "is", "are", "am", "was", "were", "do", "does", "did", "can", "could",
    "would", "will", "shall", "should", "may", "might", "have", "has", "had",
    "isn't", "aren't", "don't", "doesn't", "didn't", "can't", "couldn't",
    "wouldn't", "won't", "shouldn't",
}


def at_sentence_start(before: str) -> bool:
    """True if text inserted after `before` begins a new sentence."""
    stripped = before.rstrip()
    if stripped == "":
        return True
    return stripped[-1] in _SENTENCE_BOUNDARY


def _is_proper(word: str, vocab_terms: list[str]) -> bool:
    """Keep a word's capitalization mid-sentence only if it's 'I' or a name we
    know from vocab. (Whisper capitalizes every first word, so casing alone
    can't tell us it's a proper noun.)"""
    if word == "I" or word.startswith("I'"):
        return True
    w = word.strip(".,!?;:'\"").lower()
    for term in vocab_terms:
        # match the term or its first token, case-insensitively
        if w and (w == term.lower() or term.lower().split()[:1] == [w]):
            return True
    return False


def _looks_like_question(text: str) -> bool:
    first = text.split(None, 1)[0].strip(".,!?;:'\"").lower() if text.split() else ""
    return first in _QUESTION_STARTERS


def format_text(
    text: str,
    before: str = "",
    context_known: bool = False,
    vocab_terms: list[str] | None = None,
) -> str:
    """Return `text` shaped for insertion after `before`.

    context_known=False (couldn't read the field) falls back to sentence-start
    behavior: capitalize + terminal mark, no leading space.
    """
    text = text.strip()
    if not text:
        return text
    vocab_terms = vocab_terms or []

    if context_known:
        start = at_sentence_start(before)
        need_leading_space = (
            not start and before != "" and not before[-1].isspace()
        )
    else:
        start, need_leading_space = True, False

    first_word = text.split(None, 1)[0]
    if start:
        text = text[0].upper() + text[1:]
    elif not _is_proper(first_word, vocab_terms):
        text = text[0].lower() + text[1:]

    if start and text[-1] not in _ENDS:
        text += "?" if _looks_like_question(text) else "."

    if need_leading_space:
        text = " " + text
    return text
