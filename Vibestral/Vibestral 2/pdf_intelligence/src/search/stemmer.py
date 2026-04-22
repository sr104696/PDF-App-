# src/search/stemmer.py
# Changes: Added stem_all() alias; kept lru_cache; graceful fallback if snowball missing.
"""Snowball English stemmer wrapper. Falls back to identity if not installed."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

try:
    import snowballstemmer  # type: ignore
    _STEMMER = snowballstemmer.stemmer("english")
    _OK = True
except Exception:
    _STEMMER = None
    _OK = False


@lru_cache(maxsize=8192)
def stem(token: str) -> str:
    if not token:
        return token
    if _OK and _STEMMER is not None:
        return _STEMMER.stemWord(token)
    # Crude fallback: lowercase + drop common English suffixes
    t = token.lower()
    for suf in ("ing", "edly", "ed", "ly", "es", "s"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def stem_all(tokens: Iterable[str]) -> List[str]:
    return [stem(t) for t in tokens]


# Alias used by Claude-style callers
stem_word  = stem
stem_words = stem_all
