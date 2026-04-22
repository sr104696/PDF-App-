# src/core/tokenizer.py
# Changes: Merged Lovable + Claude patterns; uses _lazy_nltk for safe NLTK loading;
# regex fallback always available; count_tokens uses word regex (not BPE).
"""Tokenization helpers -- tiny and pure-Python.

* word_tokens  -- for indexing & BM25 (alpha-numeric, lowercase).
* count_tokens -- cheap proxy for chunk-size budgeting.
* sentences    -- NLTK punkt if available, else regex fallback.
"""
from __future__ import annotations

import re
from typing import List

_WORD_RE  = re.compile(r"[A-Za-z][A-Za-z0-9'_-]*", re.UNICODE)
# Conservative sentence boundary: .!? followed by whitespace + uppercase/quote
_SENT_RE  = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'(\[])', re.UNICODE)

_PUNKT_OK: bool | None = None  # None=not tried, True/False=cached


def word_tokens(text: str) -> List[str]:
    """Lowercased word tokens for indexing/search."""
    if not text:
        return []
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def count_tokens(text: str) -> int:
    """Approximate token count -- used only for chunk-size budgeting."""
    if not text:
        return 0
    return sum(1 for _ in _WORD_RE.finditer(text))


def _try_punkt() -> bool:
    global _PUNKT_OK
    if _PUNKT_OK is not None:
        return _PUNKT_OK
    try:
        from .._lazy_nltk import ensure_punkt
        ensure_punkt()
        import nltk  # type: ignore
        from nltk.tokenize import sent_tokenize  # noqa: F401
        # Quick smoke test
        sent_tokenize("Hello world. Test.")
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
    return [p.strip() for p in parts if p.strip()] or [text]
