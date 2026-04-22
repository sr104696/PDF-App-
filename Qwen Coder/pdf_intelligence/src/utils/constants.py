"""
Constants Module - Unchanged from original.
"""
import os


APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(APP_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "library.db")
SYNONYMS_PATH = os.path.join(DATA_DIR, "synonyms.json")
MAX_CHUNK_TOKENS = 512
