"""
schema.py — SQLite DDL, FTS5 virtual table, triggers, and connection factory.

Schema mirrors the v2 architecture (sheet 21 DATA STORES):
  documents       — one row per indexed file
  pages_chunks    — one row per semantic chunk
  term_freq       — per-chunk term counts  (BM25 TF component)
  term_df         — corpus-wide doc frequency (BM25 IDF component)
  doc_tags        — user-assigned tags (faceted filtering)
  search_history  — last N queries (optional feature)
  chunks_fts      — FTS5 virtual table; triggers keep it in sync

FTS5 tokenizer: unicode61 with diacritic removal for robust Unicode search.

NOTE: indexedAt / searchedAt use strftime('%s','now') instead of unixepoch()
for compatibility with SQLite < 3.38 (unixepoch() added in 3.38).
"""
import sqlite3
import os
from src.utils.constants import DB_PATH, SQLITE_PAGE_CACHE_KB, SQLITE_MMAP_SIZE

_SCHEMA_VERSION = 2


def _get_raw_conn(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_connection(path: str = DB_PATH) -> sqlite3.Connection:
    """
    Open a database connection with performance pragmas applied.
    WAL mode allows concurrent readers during writes (one writer at a time).
    """
    conn = _get_raw_conn(path)
    conn.executescript(f"""
        PRAGMA journal_mode   = WAL;
        PRAGMA synchronous    = NORMAL;
        PRAGMA cache_size     = -{SQLITE_PAGE_CACHE_KB};
        PRAGMA mmap_size      = {SQLITE_MMAP_SIZE};
        PRAGMA temp_store     = MEMORY;
        PRAGMA foreign_keys   = ON;
    """)
    return conn


# ── DDL ───────────────────────────────────────────────────────────────────────
# strftime('%s','now') returns Unix timestamp as text; CAST to REAL for math.
# Compatible with SQLite >= 3.8 (released 2013).
_DDL = """
-- ── Documents ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    filePath    TEXT UNIQUE NOT NULL,
    pageCount   INTEGER DEFAULT 0,
    indexedAt   REAL    DEFAULT (CAST(strftime('%s','now') AS REAL)),
    fileSize    INTEGER DEFAULT 0,
    author      TEXT,
    year        TEXT,
    language    TEXT,
    fileType    TEXT,
    collection  TEXT,
    fileMtime   REAL    NOT NULL,
    totalTokens INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_docs_author    ON documents(author);
CREATE INDEX IF NOT EXISTS idx_docs_year      ON documents(year);
CREATE INDEX IF NOT EXISTS idx_docs_filetype  ON documents(fileType);
CREATE INDEX IF NOT EXISTS idx_docs_mtime     ON documents(fileMtime);

-- ── Chunks ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pages_chunks (
    id            TEXT PRIMARY KEY,
    docId         TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    pageNum       INTEGER NOT NULL,
    chunkId       TEXT NOT NULL,
    content       TEXT NOT NULL,
    sectionHeader TEXT,
    startChar     INTEGER DEFAULT 0,
    endChar       INTEGER DEFAULT 0,
    tokenCount    INTEGER DEFAULT 0,
    prevId        TEXT,
    nextId        TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_docid   ON pages_chunks(docId);
CREATE INDEX IF NOT EXISTS idx_chunks_page    ON pages_chunks(docId, pageNum);

-- ── BM25 term statistics ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS term_freq (
    chunkId TEXT NOT NULL,
    docId   TEXT NOT NULL,
    term    TEXT NOT NULL,
    tf      INTEGER DEFAULT 1,
    PRIMARY KEY (chunkId, term),
    FOREIGN KEY (docId) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tf_term  ON term_freq(term);
CREATE INDEX IF NOT EXISTS idx_tf_docid ON term_freq(docId);

CREATE TABLE IF NOT EXISTS term_df (
    term    TEXT PRIMARY KEY,
    df      INTEGER DEFAULT 0
);

-- ── Facets: user-assigned tags ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doc_tags (
    docId   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (docId, tag)
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON doc_tags(tag);

-- ── Search history ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS search_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT NOT NULL,
    searchedAt REAL DEFAULT (CAST(strftime('%s','now') AS REAL))
);

-- ── Schema version tracker ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ── FTS5 virtual table ──────────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    sectionHeader,
    docId     UNINDEXED,
    chunkId   UNINDEXED,
    content='pages_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- ── Triggers to keep FTS in sync ────────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS chunks_ai
AFTER INSERT ON pages_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content, sectionHeader, docId, chunkId)
    VALUES (new.rowid, new.content, new.sectionHeader, new.docId, new.chunkId);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad
AFTER DELETE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, sectionHeader, docId, chunkId)
    VALUES ('delete', old.rowid, old.content, old.sectionHeader, old.docId, old.chunkId);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au
AFTER UPDATE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, sectionHeader, docId, chunkId)
    VALUES ('delete', old.rowid, old.content, old.sectionHeader, old.docId, old.chunkId);
    INSERT INTO chunks_fts(rowid, content, sectionHeader, docId, chunkId)
    VALUES (new.rowid, new.content, new.sectionHeader, new.docId, new.chunkId);
END;
"""


def initialize_db(path: str = DB_PATH) -> None:
    """
    Create all tables, indexes, triggers, and FTS5 virtual table.
    Safe to call on an existing database (IF NOT EXISTS guards).
    """
    conn = get_db_connection(path)
    try:
        conn.executescript(_DDL)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
