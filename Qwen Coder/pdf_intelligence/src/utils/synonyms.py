"""
Synonyms Module - Unchanged from original.
"""
import json
import os
from typing import Dict

from src.utils.constants import SYNONYMS_PATH


def load_synonyms() -> Dict[str, list]:
    """
    Load synonyms from the JSON file.
    
    Returns:
        Dictionary of synonyms, or empty dict if file doesn't exist or is invalid.
    """
    if os.path.exists(SYNONYMS_PATH):
        try:
            with open(SYNONYMS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_synonyms(synonyms: Dict[str, list]) -> None:
    """
    Save synonyms to the JSON file.
    
    Args:
        synonyms: Dictionary of synonyms to save.
    """
    with open(SYNONYMS_PATH, "w", encoding="utf-8") as f:
        json.dump(synonyms, f, indent=4)
