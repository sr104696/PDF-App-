"""
Shared utilities: tokenization, stemming, synonyms, hashing, file openers.
"""
import hashlib
import re
import platform
import os
import subprocess
from typing import List, Set, Dict

try:
    import snowballstemmer
    STEMMER = snowballstemmer.stemmer('english')
except Exception:
    STEMMER = None

# ---------------------------------------------------------------------------
# Stop words
# ---------------------------------------------------------------------------
STOP_WORDS = set([
    "a","an","and","are","as","at","be","by","for","from","has","he","in",
    "is","it","its","of","on","that","the","to","was","will","with","or",
    "but","not","this","have","had","what","when","where","who","which",
    "their","they","them","we","our","you","your","i","me","my"
])

# ---------------------------------------------------------------------------
# Optional synonym boost (demoted per v2; not primary mechanism)
# ---------------------------------------------------------------------------
_SYNONYMS = {
    "love": ["affection","devotion","passion"],
    "happy": ["joy","pleased","content"],
    "think": ["believe","consider","ponder"],
    "say": ["state","declare","assert"],
    "good": ["excellent","positive","virtuous"],
    "bad": ["poor","negative","harmful"],
    "important": ["significant","crucial","vital"],
    "change": ["transform","alter","modify"],
    "knowledge": ["wisdom","understanding","insight"],
    "freedom": ["liberty","independence","autonomy"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha1_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())

def stem_tokens(tokens: List[str]) -> List[str]:
    if STEMMER is None:
        return tokens
    return [STEMMER.stemWord(t) for t in tokens]

def remove_stopwords(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in STOP_WORDS]

def expand_synonyms(tokens: List[str]) -> Set[str]:
    expanded = set(tokens)
    for t in tokens:
        if t in _SYNONYMS:
            expanded.update(_SYNONYMS[t])
    return expanded

def open_file(path: str):
    """Cross-platform open with default app."""
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])
