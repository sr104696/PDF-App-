"""Tokenization helpers — keep tiny and pure-Python.

* `word_tokens` — for indexing & BM25 (alpha-numeric, lowercase).
* `count_tokens` — cheap proxy for chunk-size budgeting (no real tokenizer).
* `sentences`   — uses NLTK punkt if installed and downloaded, else regex.
"""
from __future__ import annotations

import re
from typing import List

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]*", re.UNICODE)
# Sentence boundary fallback. Conservative: split on .!? followed by space+upper.
_SENT_RE = re.compile(r"(?<=[\.!?])\s+(?=[A-Z\"'\(\[])")

_PUNKT_OK: bool | None = None  # tri-state: None=not tried, True/False=cached


def word_tokens(text: str) -> List[str]:
    """Lowercased word tokens for indexing/search."""
    if not text:
        return []
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def count_tokens(text: str) -> int:
    """Approximate token count — used only for chunk-size budgeting."""
    if not text:
        return 0
    # Word count is a fine proxy; we don't ship a real BPE tokenizer (would add MBs).
    return sum(1 for _ in _WORD_RE.finditer(text))


def _try_punkt() -> bool:
    global _PUNKT_OK
    if _PUNKT_OK is not None:
        return _PUNKT_OK
    try:
        import nltk  # type: ignore
        from nltk.tokenize import sent_tokenize  # noqa: F401
        from .._lazy_nltk import ensure_punkt
        ensure_punkt()
        _PUNKT_OK = True
    except Exception:
        _PUNKT_OK = False
    return _PUNKT_OK


def sentences(text: str) -> List[str]:
    """Best-effort sentence split. Always returns at least [text] for non-empty input."""
    text = text.strip()
    if not text:
        return []
    if _try_punkt():
        try:
            from nltk.tokenize import sent_tokenize  # type: ignore
            return [s.strip() for s in sent_tokenize(text) if s.strip()]
        except Exception:
            pass
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]
