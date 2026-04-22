"""
synonyms.py — Optional synonym boost dictionary.

Per sheet 8 (v2 status note): this is an ADDITIVE BOOST layer only.
It is NOT the primary semantic mechanism — that role belongs to Snowball
stemming + BM25. Synonyms add a small score bonus (SYNONYM_BOOST constant)
when a synonym of a query term appears in a result chunk.

The dictionary is loaded from data/synonyms.json so users can extend it.
The built-in fallback covers ~60 common English concepts.
"""
import json
import os
from src.utils.constants import SYNONYMS_PATH


# ── Built-in fallback dictionary ─────────────────────────────────────────────
_BUILTIN: dict[str, list[str]] = {
    # Emotions & states
    "love":      ["affection", "devotion", "passion", "adoration", "fondness"],
    "hate":      ["loathing", "despise", "detest", "abhor", "animosity"],
    "happy":     ["joy", "pleased", "content", "elated", "cheerful", "delight"],
    "sad":       ["sorrowful", "unhappy", "melancholy", "grief", "dejected"],
    "fear":      ["afraid", "terror", "dread", "anxiety", "panic", "fright"],
    "anger":     ["rage", "fury", "wrath", "irritation", "resentment"],
    # Philosophy & abstract
    "truth":     ["reality", "fact", "verity", "actuality", "certainty"],
    "beauty":    ["elegance", "grace", "aesthetic", "splendor", "loveliness"],
    "justice":   ["fairness", "equity", "righteousness", "impartiality"],
    "freedom":   ["liberty", "independence", "autonomy", "emancipation"],
    "power":     ["authority", "control", "influence", "dominion", "strength"],
    "knowledge": ["wisdom", "understanding", "insight", "learning", "education"],
    # Actions
    "think":     ["believe", "consider", "ponder", "reflect", "contemplate"],
    "say":       ["state", "declare", "assert", "claim", "express", "utter"],
    "show":      ["demonstrate", "reveal", "display", "exhibit", "illustrate"],
    "change":    ["transform", "alter", "modify", "shift", "evolve"],
    "begin":     ["start", "commence", "initiate", "launch", "originate"],
    "end":       ["finish", "conclude", "terminate", "complete", "close"],
    "help":      ["assist", "support", "aid", "facilitate", "enable"],
    "create":    ["build", "make", "produce", "generate", "construct"],
    # Science / tech
    "machine":   ["computer", "device", "system", "apparatus", "engine"],
    "learn":     ["train", "study", "acquire", "understand", "absorb"],
    "data":      ["information", "dataset", "records", "statistics", "figures"],
    "model":     ["network", "algorithm", "system", "framework", "architecture"],
    "search":    ["query", "lookup", "retrieve", "find", "seek"],
    "fast":      ["quick", "rapid", "swift", "efficient", "performant"],
    "error":     ["bug", "fault", "failure", "exception", "defect", "issue"],
    # Literature / humanities
    "story":     ["narrative", "tale", "account", "anecdote", "plot"],
    "leader":    ["ruler", "commander", "chief", "head", "authority", "guide"],
    "war":       ["conflict", "battle", "combat", "struggle", "strife"],
    "death":     ["mortality", "demise", "end", "passing", "loss"],
    "life":      ["existence", "living", "vitality", "being", "survival"],
    "society":   ["community", "culture", "civilization", "people", "public"],
    "law":       ["rule", "regulation", "statute", "legislation", "ordinance"],
    "economy":   ["market", "trade", "commerce", "finance", "industry"],
}


def _load() -> dict[str, list[str]]:
    """Load from JSON file, merging with built-ins. File wins on conflicts."""
    merged = dict(_BUILTIN)
    if os.path.exists(SYNONYMS_PATH):
        try:
            with open(SYNONYMS_PATH, "r", encoding="utf-8") as fh:
                user = json.load(fh)
            if isinstance(user, dict):
                merged.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    return merged


# Module-level cache; reloaded on first import only.
_CACHE: dict[str, list[str]] | None = None


def get_synonyms() -> dict[str, list[str]]:
    """Return the synonym dictionary (cached after first load)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def reload() -> None:
    """Force a reload from disk (call after user edits the JSON file)."""
    global _CACHE
    _CACHE = None


def save(synonyms: dict[str, list[str]]) -> None:
    """Persist the given dictionary to data/synonyms.json."""
    os.makedirs(os.path.dirname(SYNONYMS_PATH), exist_ok=True)
    with open(SYNONYMS_PATH, "w", encoding="utf-8") as fh:
        json.dump(synonyms, fh, indent=2, ensure_ascii=False)
    reload()


def expand(word: str) -> list[str]:
    """Return synonym list for *word* (lowercase). Empty list if none."""
    return get_synonyms().get(word.lower(), [])
