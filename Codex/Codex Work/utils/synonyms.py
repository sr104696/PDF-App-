import json
import os
from functools import lru_cache
from src.utils.constants import SYNONYMS_PATH

@lru_cache(maxsize=1)
def load_synonyms() -> dict:
    if os.path.exists(SYNONYMS_PATH):
        try:
            with open(SYNONYMS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_synonyms(synonyms: dict) -> None:
    with open(SYNONYMS_PATH, "w", encoding="utf-8") as f:
        json.dump(synonyms, f, indent=4)
    # Ensure subsequent reads use the latest persisted data.
    load_synonyms.cache_clear()
