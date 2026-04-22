"""Project-wide constants. Keep cheap to import."""
from pathlib import Path

APP_NAME = "PDF Intelligence"
APP_VERSION = "1.0.0"

# Paths -----------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
DB_PATH = DATA_DIR / "library.db"
SYNONYMS_PATH = DATA_DIR / "synonyms.json"
NLTK_DATA_DIR = DATA_DIR / "nltk_data"

# Chunking --------------------------------------------------------------
MAX_CHUNK_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 32
MIN_CHUNK_TOKENS = 20

# Search ----------------------------------------------------------------
CANDIDATE_LIMIT = 200          # rerank top-N from FTS5
DEFAULT_RESULT_LIMIT = 25
BM25_K1 = 1.5
BM25_B = 0.75
SYNONYM_BOOST = 0.15           # additive, small (sheet 8: minor signal)

# Filler / stopwords (very small, not exhaustive) -----------------------
FILLER_WORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "but", "if", "in", "on", "at",
    "to", "for", "with", "by", "from", "is", "are", "was", "were", "be",
    "been", "being", "as", "that", "this", "these", "those", "it", "its",
    "what", "which", "who", "whom", "how", "why", "where", "when",
    "please", "tell", "me", "about", "show", "give", "find",
})

SUPPORTED_EXTS = {".pdf", ".epub"}
