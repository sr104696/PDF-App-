"""
constants.py — Application-wide configuration constants.
All tunable parameters live here so they can be adjusted without
hunting through individual modules.
"""
import os
import sys

# ── Path resolution ──────────────────────────────────────────────────────────
# When frozen by PyInstaller, __file__ points inside the temp dir.
# We want DATA_DIR to live alongside the executable / project root.
if getattr(sys, "frozen", False):
    _APP_ROOT = os.path.dirname(sys.executable)
else:
    # src/utils/constants.py → go up three levels to reach project root
    _APP_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

APP_ROOT = _APP_ROOT
DATA_DIR = os.path.join(APP_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "library.db")
SYNONYMS_PATH = os.path.join(DATA_DIR, "synonyms.json")
NLTK_DATA_DIR = os.path.join(DATA_DIR, "nltk_data")

# ── Chunking parameters ──────────────────────────────────────────────────────
MAX_CHUNK_TOKENS = 512      # hard cap per chunk (word-count proxy)
MIN_CHUNK_TOKENS = 20       # tiny tail fragments are merged into prev chunk
CHUNK_OVERLAP_TOKENS = 32   # tokens carried from end of prev chunk to next
CHUNK_HARD_CAP = 800        # absolute emergency cap; split here no matter what

# ── Search parameters ────────────────────────────────────────────────────────
CANDIDATE_LIMIT = 200       # FTS5 candidate pool before BM25 rerank
TOP_K_DEFAULT = 20          # results returned to UI
SYNONYM_BOOST = 0.15        # additive score bonus for synonym hits
BM25_K1 = 1.5               # BM25 term-saturation parameter
BM25_B = 0.75               # BM25 length-normalisation parameter
BM25_EPSILON = 0.25         # floor for negative IDF terms (Okapi variant)

# ── UI parameters ────────────────────────────────────────────────────────────
APP_TITLE = "PDF Intelligence"
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700
SEARCH_HISTORY_MAX = 10     # last N queries stored in SQLite

# ── SQLite tuning ────────────────────────────────────────────────────────────
SQLITE_PAGE_CACHE_KB = 20_000   # 20 MB page cache
SQLITE_MMAP_SIZE = 256 * 1024 * 1024  # 256 MB mmap hint

# ── Supported formats ────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".epub"}
