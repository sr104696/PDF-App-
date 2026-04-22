# src/utils/synonyms.py
# Changes: No functional changes from Lovable; kept lru_cache lazy load pattern.
"""Static synonym dictionary (sheet 8). Additive boost only -- never primary retrieval.
Loaded lazily from data/synonyms.json so users can edit without recompiling."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, FrozenSet

from .constants import SYNONYMS_PATH

_BUILTIN: Dict[str, list[str]] = {
    "car":    ["automobile", "vehicle"],
    "buy":    ["purchase", "acquire"],
    "fast":   ["quick", "rapid", "swift"],
    "big":    ["large", "huge"],
    "small":  ["tiny", "little"],
    "doctor": ["physician"],
    "ai":     ["artificial intelligence", "machine learning"],
    "book":   ["novel", "text", "volume"],
    "write":  ["author", "compose"],
    "death":  ["mortality", "dying"],
    "love":   ["affection", "passion"],
}


@lru_cache(maxsize=1)
def _load() -> Dict[str, FrozenSet[str]]:
    raw: Dict[str, list[str]] = dict(_BUILTIN)
    try:
        if SYNONYMS_PATH.exists():
            with open(SYNONYMS_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                for k, v in user.items():
                    if isinstance(v, list):
                        raw[k.lower()] = [str(x).lower() for x in v]
    except Exception:
        pass  # synonyms are non-critical; never crash over them
    return {k.lower(): frozenset(v) for k, v in raw.items()}


def expand(token: str) -> FrozenSet[str]:
    """Return synonyms for a single lowercase token (excluding the token itself)."""
    return _load().get(token.lower(), frozenset())
