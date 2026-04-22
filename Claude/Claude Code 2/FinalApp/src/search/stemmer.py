"""Snowball English stemmer with LRU cache and graceful fallback."""
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

_SUFFIXES = ("ing", "edly", "tion", "tions", "ed", "ly", "es", "er", "s")


@lru_cache(maxsize=16384)
def stem(token: str) -> str:
    """Return the Snowball stem of a lowercase token."""
    if not token:
        return token
    t = token.lower()
    if _OK and _STEMMER is not None:
        return _STEMMER.stemWord(t)
    # crude fallback
    for suf in _SUFFIXES:
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def stem_all(tokens: Iterable[str]) -> List[str]:
    return [stem(t) for t in tokens]
