"""Static synonym dictionary (sheet 8). Used as a small additive boost only —
never as the primary retrieval mechanism. Loaded lazily from data/synonyms.json
so users can edit without recompiling."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, FrozenSet

from .constants import SYNONYMS_PATH

# Tiny built-in fallback so the app works before the user customizes the file.
_BUILTIN: Dict[str, list[str]] = {
    "car": ["automobile", "vehicle"],
    "buy": ["purchase", "acquire"],
    "fast": ["quick", "rapid", "swift"],
    "big": ["large", "huge"],
    "small": ["tiny", "little"],
    "doctor": ["physician"],
    "ai": ["artificial intelligence", "machine learning"],
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
        # Synonyms are non-critical; never crash the app over them.
        pass
    return {k.lower(): frozenset(v) for k, v in raw.items()}


def expand(token: str) -> FrozenSet[str]:
    """Return synonyms for a single lowercase token (excluding the token itself)."""
    return _load().get(token.lower(), frozenset())
