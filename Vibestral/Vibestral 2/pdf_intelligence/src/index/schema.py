# src/index/schema.py
# Changes: Kept Lovable's INTEGER PK for documents (simpler than TEXT SHA1 PK);
# added Claude's mmap_size pragma; fixed mojibake in comments; added doc_tags table.
"""SQLite schema (sheet 6 + v2 extensions).

Tables
------
documents      -- one row per indexed file
pages_chunks   -- semantic chunks (sheet 14)
term_freq      -- per-chunk token frequencies (BM25 on chunk granularity)
term_df        -- corpus-wide document frequency per stem
chunks_fts     -- FTS5 virtual table over chunk text (candidate generation)
doc_tags       -- user-assigned tags (faceted filtering)
meta           -- key/value app state (schema version, etc.)
search_history -- saved searches (sheet 16)

FTS5 for fast candidate retrieval; our own BM25 for rerank (two-phase).
BM25 stats stored at CHUNK level -- not document level -- for accuracy.
"""
from __future__ import annotations

import sqlite3

from ..utils.constants import DB_PATH, SQLITE_PAGE_CACHE_KB, SQLITE_MMAP_SIZE

SCHEMA_VERSION = 2

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    file_path    TEXT NOT NULL UNIQUE,
    file_type    TEXT NOT NULL,
    page_count   INTEGER NOT NULL DEFAULT 0,
    file_size    INTEGER NOT NULL DEFAULT 0,
    file_mtime   REAL    NOT NULL DEFAULT 0,
    indexed_at   REAL    NOT NULL,
    author       TEXT,
    year         INTEGER,
    language     TEXT,
    collection   TEXT,
    total_tokens INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection);
CREATE INDEX IF NOT EXISTS idx_documents_author     ON documents(author);
CREATE INDEX IF NOT EXISTS idx_documents_year       ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_filetype   ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_documents_mtime      ON documents(file_mtime);

CREATE TABLE IF NOT EXISTS pages_chunks (
    id              TEXT PRIMARY KEY,
    doc_id          INTEGER NOT NULL,
    page_num        INTEGER NOT NULL,
    chunk_idx       INTEGER NOT NULL,
    content         TEXT    NOT NULL,
    section_header  TEXT,
    start_char      INTEGER NOT NULL,
    end_char        INTEGER NOT NULL,
    token_count     INTEGER NOT NULL,
    prev_id         TEXT,
    next_id         TEXT,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_page ON pages_chunks(doc_id, page_num);
CREATE INDEX IF NOT EXISTS idx_chunks_docid    ON pages_chunks(doc_id);

-- BM25 statistics at CHUNK level (not document level -- avoids length bias)
CREATE TABLE IF NOT EXISTS term_freq (
    chunk_id TEXT NOT NULL,
    term     TEXT NOT NULL,
    tf       INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, term),
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_term_freq_term ON term_freq(term);

CREATE TABLE IF NOT EXISTS term_df (
    term TEXT PRIMARY KEY,
    df   INTEGER NOT NULL
);

-- User-assigned tags for faceted filtering
CREATE TABLE IF NOT EXISTS doc_tags (
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag    TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_doc_tags_tag ON doc_tags(tag);

-- FTS5 candidate index (content stored in pages_chunks -- saves space)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='pages_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- Keep FTS in sync via triggers
CREATE TRIGGER IF NOT EXISTS pages_chunks_ai AFTER INSERT ON pages_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS pages_chunks_ad AFTER DELETE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS pages_chunks_au AFTER UPDATE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TABLE IF NOT EXISTS search_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def open_db(path=None) -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection with performance pragmas applied."""
    if path is None:
        path = DB_PATH
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA cache_size=-{SQLITE_PAGE_CACHE_KB}")
    conn.execute(f"PRAGMA mmap_size={SQLITE_MMAP_SIZE}")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
