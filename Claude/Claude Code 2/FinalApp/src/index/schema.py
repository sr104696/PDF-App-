"""SQLite schema — full holistic architecture.

Core tables (from Lovable baseline + Qwen Coder fixes):
  documents, pages_chunks, term_freq, term_df, chunks_fts,
  search_history, doc_tags, meta

New tables (holistic architecture):
  chunk_concepts    — pre-computed concept terms per chunk (for fast concept scoring)
  term_cooccurrence — corpus-calibrated co-occurrence pairs
  chunk_structure   — structure_type + density per chunk
  chunk_embeddings  — optional dense vectors (bge-micro)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..utils.constants import DB_PATH

SCHEMA_VERSION = 3

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-20480;
PRAGMA foreign_keys=ON;

-- ── Core ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,          -- SHA1 of file path
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

CREATE INDEX IF NOT EXISTS idx_doc_collection ON documents(collection);
CREATE INDEX IF NOT EXISTS idx_doc_author     ON documents(author);
CREATE INDEX IF NOT EXISTS idx_doc_year       ON documents(year);
CREATE INDEX IF NOT EXISTS idx_doc_mtime      ON documents(file_mtime);

CREATE TABLE IF NOT EXISTS pages_chunks (
    id              TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    page_num        INTEGER NOT NULL,
    chunk_idx       INTEGER NOT NULL DEFAULT 0,
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

-- BM25 statistics ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS term_freq (
    chunk_id TEXT NOT NULL,
    doc_id   TEXT NOT NULL,
    term     TEXT NOT NULL,
    tf       INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, term),
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tf_term    ON term_freq(term);
CREATE INDEX IF NOT EXISTS idx_tf_doc     ON term_freq(doc_id);

CREATE TABLE IF NOT EXISTS term_df (
    term TEXT PRIMARY KEY,
    df   INTEGER NOT NULL
);

-- FTS5 ────────────────────────────────────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='pages_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS pc_ai AFTER INSERT ON pages_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS pc_ad AFTER DELETE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS pc_au AFTER UPDATE ON pages_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

-- ── Holistic architecture tables ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chunk_structure (
    chunk_id       TEXT PRIMARY KEY,
    structure_type TEXT NOT NULL DEFAULT 'exposition',
    density_score  REAL NOT NULL DEFAULT 0.1,
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunk_concepts (
    chunk_id TEXT NOT NULL,
    concept  TEXT NOT NULL,       -- stemmed concept term
    source   TEXT NOT NULL,       -- 'direct' | 'concept' | 'cooc'
    weight   REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (chunk_id, concept),
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cc_concept ON chunk_concepts(concept);

CREATE TABLE IF NOT EXISTS term_cooccurrence (
    term_a TEXT NOT NULL,
    term_b TEXT NOT NULL,
    count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (term_a, term_b)
);
CREATE INDEX IF NOT EXISTS idx_cooc_a ON term_cooccurrence(term_a);
CREATE INDEX IF NOT EXISTS idx_cooc_b ON term_cooccurrence(term_b);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id      TEXT PRIMARY KEY,
    embedding     BLOB NOT NULL,     -- packed float32 array (384 dims for bge-micro)
    model_version TEXT NOT NULL,
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);

-- ── Extras ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS doc_tags (
    doc_id TEXT NOT NULL,
    tag    TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS search_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query      TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    # Store schema version
    conn.execute(
        "INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn
