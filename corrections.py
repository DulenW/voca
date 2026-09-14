"""corrections.py — SQLite learning layer: corrections + vocab.

Two tables (spec.md "Learning layer"), stored in the app support dir:
  corrections(id, wrong_text, correct_text, hit_count, created_at)
  vocab(id, term, created_at)

Usage:
  - vocab_prompt(): join all terms into one string, passed to mlx-whisper as
    initial_prompt so names/brands/jargon are spelled correctly.
  - apply_corrections(text): case-insensitive WHOLE-WORD replacement of
    wrong_text -> correct_text, incrementing hit_count for each fix applied.

A new connection is opened per call (check_same_thread safe): menu actions run
on the main thread while transcription/correction runs on a worker thread.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone

from config import APP_DIR

DB_PATH = os.path.join(APP_DIR, "voca.sqlite")


def _connect() -> sqlite3.Connection:
    os.makedirs(APP_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _connect() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS corrections(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wrong_text   TEXT NOT NULL,
                correct_text TEXT NOT NULL,
                hit_count    INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS vocab(
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                term       TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL)"""
        )


# --- vocab -----------------------------------------------------------------
def add_vocab(term: str) -> bool:
    """Add a vocab term. Returns False if empty or a duplicate."""
    term = term.strip()
    if not term:
        return False
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO vocab(term, created_at) VALUES(?, ?)", (term, _now())
            )
        return True
    except sqlite3.IntegrityError:  # UNIQUE violation
        return False


def list_vocab() -> list[sqlite3.Row]:
    with _connect() as c:
        return c.execute(
            "SELECT * FROM vocab ORDER BY term COLLATE NOCASE"
        ).fetchall()


def delete_vocab(vocab_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))


def vocab_prompt() -> str | None:
    """All vocab terms as one comma-separated string for Whisper's
    initial_prompt, or None if there are none."""
    terms = [r["term"] for r in list_vocab()]
    return ", ".join(terms) if terms else None


# --- corrections -----------------------------------------------------------
def add_correction(wrong: str, correct: str) -> bool:
    """Add a wrong->correct mapping. Returns False if either side is empty."""
    wrong, correct = wrong.strip(), correct.strip()
    if not wrong or not correct:
        return False
    with _connect() as c:
        c.execute(
            "INSERT INTO corrections(wrong_text, correct_text, hit_count, "
            "created_at) VALUES(?, ?, 0, ?)",
            (wrong, correct, _now()),
        )
    return True


def list_corrections() -> list[sqlite3.Row]:
    with _connect() as c:
        return c.execute(
            "SELECT * FROM corrections ORDER BY hit_count DESC, id"
        ).fetchall()


def delete_correction(correction_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM corrections WHERE id = ?", (correction_id,))


def apply_corrections(text: str) -> str:
    """Apply every correction as a case-insensitive whole-word replacement,
    incrementing hit_count by the number of replacements made."""
    if not text:
        return text
    rows = list_corrections()
    with _connect() as c:
        for r in rows:
            pattern = re.compile(
                r"\b" + re.escape(r["wrong_text"]) + r"\b", re.IGNORECASE
            )
            text, n = pattern.subn(r["correct_text"], text)
            if n:
                c.execute(
                    "UPDATE corrections SET hit_count = hit_count + ? WHERE id = ?",
                    (n, r["id"]),
                )
    return text
