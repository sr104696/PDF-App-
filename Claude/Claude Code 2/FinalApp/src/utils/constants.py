"""Project-wide constants. Cheap to import — no heavy deps."""
from pathlib import Path

APP_NAME    = "PDF Intelligence"
APP_VERSION = "2.0.0"

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).resolve().parents[2]
DATA_DIR      = ROOT_DIR / "data"
ASSETS_DIR    = ROOT_DIR / "assets"
DB_PATH       = DATA_DIR / "library.db"
SYNONYMS_PATH = DATA_DIR / "synonyms.json"
NLTK_DATA_DIR = DATA_DIR / "nltk_data"
EMBED_MODEL_DIR = DATA_DIR / "models"
EMBED_MODEL_PATH = EMBED_MODEL_DIR / "bge-micro-v2.onnx"
EMBED_TOKENIZER_PATH = EMBED_MODEL_DIR / "tokenizer.json"

# ── Chunking ────────────────────────────────────────────────────────────────
MAX_CHUNK_TOKENS     = 512
CHUNK_OVERLAP_TOKENS = 32
MIN_CHUNK_TOKENS     = 20

# ── Search ──────────────────────────────────────────────────────────────────
CANDIDATE_LIMIT      = 300   # wider net for multi-signal reranker
DEFAULT_RESULT_LIMIT = 25
COOCCUR_WINDOW       = 50    # token window for co-occurrence pairs
COOCCUR_TOPK         = 10    # top co-occurrence terms to use per query atom
EMBED_TOPK           = 300   # max chunks to embed-score (over BM25 candidates)
JACCARD_DUP_THRESH   = 0.70  # result dedup threshold

# ── BM25 ────────────────────────────────────────────────────────────────────
BM25_K1 = 1.5
BM25_B  = 0.75

# ── Multi-signal scorer weights ─────────────────────────────────────────────
W_STEM   = 1.00   # BM25 on query stems
W_SYN    = 0.85   # BM25 on direct synonyms
W_CON    = 0.60   # BM25 on conceptual neighbors
W_COOC   = 0.45   # corpus co-occurrence signal
W_STRUCT = 0.30   # structural intent bonus (additive flat bonus)
W_EMB    = 0.30   # embedding cosine similarity
W_PROX   = 0.20   # both atoms in same/adjacent chunk bonus
W_HDR    = 0.15   # query terms appear in section header

# ── Feature flags ───────────────────────────────────────────────────────────
EMBEDDING_ENABLED = False   # flipped True at runtime if model present

# ── Stop / filler words ─────────────────────────────────────────────────────
FILLER_WORDS = frozenset({
    "a","an","the","of","and","or","but","if","in","on","at","to","for",
    "with","by","from","is","are","was","were","be","been","being","as",
    "that","this","these","those","it","its","what","which","who","whom",
    "how","why","where","when","please","tell","me","about","show","give",
    "find","search","get","look","some","any","all","each","every","more",
    "most","such","no","not","only","own","same","so","than","too","very",
    "just","can","will","do","did","does","have","has","had","may","might",
    "shall","should","would","could","am",
})

SUPPORTED_EXTS = {".pdf", ".epub"}
