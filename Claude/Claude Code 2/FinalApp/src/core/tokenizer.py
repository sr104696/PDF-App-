"""Tokenization and sentence splitting.

Tries NLTK Punkt first; falls back to a regex splitter that works 95% of the
time on standard prose. Token counting uses a simple word-count proxy
(avoids the ~3 MB tiktoken Rust extension).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List

from ..utils.constants import NLTK_DATA_DIR

# ── word tokeniser ──────────────────────────────────────────────────────────
_WORD_RE = re.compile(r"\b[a-zA-Z\u00C0-\u024F']+\b", re.UNICODE)

def word_tokens(text: str) -> List[str]:
    """Return lowercase word tokens (no punctuation, no numbers)."""
    return _WORD_RE.findall(text.lower())


def count_tokens(text: str) -> int:
    """Approximate token count (word proxy). Fast, no deps."""
    return max(1, len(text.split()))


# ── sentence splitter ───────────────────────────────────────────────────────
_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z\"\'\u201C\u2018])')

def _regex_sentences(text: str) -> List[str]:
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


@lru_cache(maxsize=1)
def _try_load_nltk():
    """Try to load NLTK punkt. Returns tokenizer or None."""
    try:
        import nltk  # type: ignore
        nltk.data.path.insert(0, str(NLTK_DATA_DIR))
        return nltk.data.load("tokenizers/punkt_tab/english.pickle")
    except Exception:
        try:
            import nltk  # type: ignore
            nltk.data.path.insert(0, str(NLTK_DATA_DIR))
            return nltk.data.load("tokenizers/punkt/english.pickle")
        except Exception:
            return None


def sentences(text: str) -> List[str]:
    """Split text into sentences using NLTK if available, regex otherwise."""
    tok = _try_load_nltk()
    if tok is not None:
        try:
            return [s.strip() for s in tok.tokenize(text) if s.strip()]
        except Exception:
            pass
    return _regex_sentences(text)
