"""SQLite schema (sheet 6 + v2 extensions).

Tables
------
documents      — one row per indexed file
pages_chunks   — semantic chunks (sheet 14)
term_freq      — per-chunk token frequencies (BM25 on chunk granularity)
term_df        — corpus-wide document frequency per stem
chunks_fts     — FTS5 virtual table over chunk text (candidate generation)
meta           — key/value app state (schema version, etc.)
search_history — sheet 16 saved searches

We use FTS5 for fast candidate retrieval and our own BM25 implementation for
the rerank stage (two-phase, sk-hybrid-search pattern). Reason: SQLite's
built-in BM25() works but has no synonym hooks and no easy way to access
term stats for explanation/debugging.
"""

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    file_path    TEXT NOT NULL UNIQUE,
    file_type    TEXT NOT NULL,            -- 'pdf' | 'epub'
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

CREATE TABLE IF NOT EXISTS pages_chunks (
    id              TEXT PRIMARY KEY,        -- SHA1 chunk id
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

-- BM25 statistics --------------------------------------------------------
CREATE TABLE IF NOT EXISTS term_freq (
    chunk_id TEXT NOT NULL,
    term     TEXT NOT NULL,                  -- stemmed token
    tf       INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, term),
    FOREIGN KEY (chunk_id) REFERENCES pages_chunks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_term_freq_term ON term_freq(term);

CREATE TABLE IF NOT EXISTS term_df (
    term TEXT PRIMARY KEY,
    df   INTEGER NOT NULL                    -- # of chunks containing the term
);

-- FTS5 candidate index (content stored elsewhere — saves space) ---------
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='pages_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- Keep FTS in sync via triggers.
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
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    query     TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""
