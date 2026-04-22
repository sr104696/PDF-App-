"""Three-layer query expansion network.

Each entry in synonyms.json has:
  direct   — immediate synonyms (weight W_SYN)
  concepts — thematic/emotional neighbors (weight W_CON)
  register — domain tags for cross-domain expansion

expand_atom() does a two-hop walk:
  Hop 1: direct + concepts of the query term.
  Hop 2: direct of each direct synonym (so "love → devotion → loyalty" etc.)

Returns three separate sets so the scorer can weight them independently.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, FrozenSet, Set, Tuple

from .constants import SYNONYMS_PATH

log = logging.getLogger(__name__)

_BUILTIN: Dict[str, dict] = {
    "love":  {"direct": ["affection","devotion","tenderness"], "concepts": ["longing","intimacy"], "register": ["emotional"]},
    "loss":  {"direct": ["grief","sorrow","absence"], "concepts": ["elegy","impermanence","yearning"], "register": ["grief"]},
    "fear":  {"direct": ["dread","terror","anxiety"], "concepts": ["courage","danger"], "register": ["emotional"]},
    "joy":   {"direct": ["happiness","delight","bliss"], "concepts": ["wonder","beauty"], "register": ["emotional"]},
    "truth": {"direct": ["reality","honesty","veracity"], "concepts": ["knowledge","clarity"], "register": ["philosophical"]},
}

MAX_EXPANSION_TERMS = 40  # hard cap per atom to prevent runaway


@dataclass
class AtomExpansion:
    """Weighted expansion for one semantic atom."""
    atom: str
    direct: FrozenSet[str]    # weight W_SYN
    concepts: FrozenSet[str]  # weight W_CON
    registers: FrozenSet[str] # domain tags


@lru_cache(maxsize=1)
def _load_raw() -> Dict[str, dict]:
    raw: Dict[str, dict] = dict(_BUILTIN)
    try:
        if SYNONYMS_PATH.exists():
            with open(SYNONYMS_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict):
                    raw[k.lower()] = {
                        "direct":   [str(x).lower() for x in v.get("direct", [])],
                        "concepts": [str(x).lower() for x in v.get("concepts", [])],
                        "register": [str(x).lower() for x in v.get("register", [])],
                    }
    except Exception as e:
        log.warning("Could not load synonyms.json: %s", e)
    return raw


def _db() -> Dict[str, dict]:
    return _load_raw()


def _get_entry(term: str) -> dict:
    db = _db()
    return db.get(term.lower(), {"direct": [], "concepts": [], "register": []})


def expand_atom(atom: str) -> AtomExpansion:
    """Two-hop expansion for a single query atom (already lowercased)."""
    entry = _get_entry(atom)
    direct_set: Set[str] = set(entry["direct"])
    concept_set: Set[str] = set(entry["concepts"])
    register_set: Set[str] = set(entry["register"])

    # Hop 2: grab 'direct' synonyms of our direct synonyms
    for syn in list(direct_set):
        sub = _get_entry(syn)
        for t in sub.get("direct", []):
            direct_set.add(t)
        for t in sub.get("concepts", []):
            concept_set.add(t)

    # Remove the atom itself
    direct_set.discard(atom)
    concept_set.discard(atom)
    direct_set -= concept_set  # keep sets disjoint

    # Cap to prevent explosion
    direct_list  = list(direct_set)[:MAX_EXPANSION_TERMS]
    concept_list = list(concept_set)[:MAX_EXPANSION_TERMS]

    return AtomExpansion(
        atom=atom,
        direct=frozenset(direct_list),
        concepts=frozenset(concept_list),
        registers=frozenset(register_set),
    )


def invalidate_cache() -> None:
    """Call after saving a new synonyms.json so changes take effect."""
    _load_raw.cache_clear()


def all_keys() -> list[str]:
    return list(_db().keys())
