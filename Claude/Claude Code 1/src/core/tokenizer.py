"""
tokenizer.py — Word and sentence tokenization.

Word tokenizer: simple regex over Unicode word characters.
  No external deps; consistent with what is stored in term_freq.

Sentence tokenizer: tries NLTK punkt (accurate), falls back to a
  punctuation-boundary regex (handles ~95 % of standard prose).
  The fallback is wired in from the start so the app never fails
  hard when NLTK data isn't available offline.
"""
import re
import os
from typing import Iterator

# ── Word tokenization ────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


def tokenize_words(text: str) -> list[str]:
    """Return lowercased word tokens from *text*."""
    return _WORD_RE.findall(text.lower())


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


# ── Sentence tokenization ────────────────────────────────────────────────────
_SENTENCE_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\"\'])",   # sentence-ending punctuation → capital
    re.UNICODE,
)


def _regex_sent_split(text: str) -> list[str]:
    """Simple regex sentence splitter — no deps, ~95 % accuracy on prose."""
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _try_punkt(text: str) -> list[str] | None:
    """
    Attempt NLTK punkt tokenisation.  Returns None if NLTK or its data
    file is not available; caller falls back to regex.
    """
    try:
        import nltk  # noqa: PLC0415  (lazy import)
        from nltk.tokenize import sent_tokenize  # noqa: PLC0415

        # Point NLTK at our local data dir so it works offline.
        from src.utils.constants import NLTK_DATA_DIR  # noqa: PLC0415
        if NLTK_DATA_DIR not in nltk.data.path:
            nltk.data.path.insert(0, NLTK_DATA_DIR)

        return sent_tokenize(text)
    except Exception:  # nltk not installed or punkt data missing
        return None


def tokenize_sentences(text: str) -> list[str]:
    """
    Split *text* into sentences.
    Uses NLTK punkt when available; regex otherwise.
    """
    result = _try_punkt(text)
    if result is not None:
        return result
    return _regex_sent_split(text) or [text]
