# src/utils/constants.py
# Changes: PyInstaller frozen-path fix (sys.frozen check), added CHUNK_HARD_CAP,
# added SQLite mmap/cache constants, expanded FILLER_WORDS to full stop-word set.
"""Project-wide constants. Cheap to import."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PDF Intelligence"
APP_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Path resolution -- works both from source and when frozen by PyInstaller
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Running as a PyInstaller one-file bundle; executable is the app root.
    _APP_ROOT = Path(sys.executable).parent
else:
    # src/utils/constants.py -> go up three levels to reach project root
    _APP_ROOT = Path(__file__).resolve().parents[3]

ROOT_DIR      = _APP_ROOT
DATA_DIR      = ROOT_DIR / "data"
ASSETS_DIR    = ROOT_DIR / "assets"
DB_PATH       = DATA_DIR / "library.db"
SYNONYMS_PATH = DATA_DIR / "synonyms.json"
NLTK_DATA_DIR = DATA_DIR / "nltk_data"

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
MAX_CHUNK_TOKENS     = 512   # target max tokens per chunk
MIN_CHUNK_TOKENS     = 20    # tiny tail fragments merged into previous chunk
CHUNK_OVERLAP_TOKENS = 32    # tokens carried from end of prev chunk (context)
CHUNK_HARD_CAP       = 800   # absolute emergency split -- no chunk exceeds this

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
CANDIDATE_LIMIT      = 200   # FTS5 candidate pool before BM25 rerank
DEFAULT_RESULT_LIMIT = 25    # results returned to UI
BM25_K1              = 1.5   # term-saturation parameter
BM25_B               = 0.75  # length-normalisation parameter
SYNONYM_BOOST        = 0.15  # additive score bonus for synonym hits

# ---------------------------------------------------------------------------
# SQLite tuning
# ---------------------------------------------------------------------------
SQLITE_PAGE_CACHE_KB = 20_000          # ~20 MB page cache
SQLITE_MMAP_SIZE     = 256 * 1024 * 1024  # 256 MB mmap hint

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
WINDOW_WIDTH  = 1080
WINDOW_HEIGHT = 720
SEARCH_HISTORY_MAX = 50

# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------
SUPPORTED_EXTS = {".pdf", ".epub"}

# ---------------------------------------------------------------------------
# Stop words (comprehensive -- used by query_parser)
# ---------------------------------------------------------------------------
FILLER_WORDS: frozenset[str] = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "a", "an", "the", "and", "but", "if", "or", "because", "as",
    "until", "while", "of", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "s", "t",
    "can", "will", "just", "don", "should", "now",
    "d", "ll", "m", "o", "re", "ve", "y",
    "ain", "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven",
    "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn",
    "wasn", "weren", "won", "wouldn",
    # extra filler for search queries
    "please", "tell", "me", "about", "show", "give", "find", "get",
    "look", "search", "want", "need", "like",
})
