"""
Database Schema Module - Optimized version with indexes for performance.
"""
import sqlite3
import os
from typing import Optional

from constants import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """
    Creates and returns a database connection.
    
    Returns:
        SQLite connection object with row factory enabled.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db() -> None:
    """
    Initializes the database schema with all required tables, indexes, and triggers.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT,
            filePath TEXT UNIQUE,
            pageCount INTEGER,
            indexedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fileSize INTEGER,
            author TEXT,
            year TEXT,
            language TEXT,
            fileType TEXT,
            collection TEXT,
            fileMtime REAL,
            totalTokens INTEGER
        )
    """)
    
    # Chunks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages_chunks (
            id TEXT PRIMARY KEY,
            docId TEXT,
            pageNum INTEGER,
            chunkId TEXT,
            content TEXT,
            sectionHeader TEXT,
            startChar INTEGER,
            endChar INTEGER,
            tokenCount INTEGER,
            prevId TEXT,
            nextId TEXT,
            FOREIGN KEY(docId) REFERENCES documents(id)
        )
    """)
    
    # FTS5 virtual table for fast full-text search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content,
            docId UNINDEXED,
            chunkId UNINDEXED,
            content='pages_chunks',
            content_rowid='rowid'
        )
    """)
    
    # Triggers to keep FTS table in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON pages_chunks BEGIN
            INSERT INTO chunks_fts(rowid, content, docId, chunkId)
            VALUES (new.rowid, new.content, new.docId, new.chunkId);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON pages_chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, content, docId, chunkId)
            VALUES ('delete', old.rowid, old.content, old.docId, old.chunkId);
        END;
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON pages_chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, content, docId, chunkId)
            VALUES ('delete', old.rowid, old.content, old.docId, old.chunkId);
            INSERT INTO chunks_fts(rowid, content, docId, chunkId)
            VALUES (new.rowid, new.content, new.docId, new.chunkId);
        END;
    """)
    
    # BM25 Statistics Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS term_df (
            term TEXT PRIMARY KEY,
            doc_freq INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS term_freq (
            docId TEXT,
            term TEXT,
            freq INTEGER,
            PRIMARY KEY (docId, term),
            FOREIGN KEY(docId) REFERENCES documents(id)
        )
    """)
    
    # Performance indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_fileMtime ON documents(fileMtime)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_fileType ON documents(fileType)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_author ON documents(author)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pages_chunks_docId ON pages_chunks(docId)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_term_freq_term ON term_freq(term)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_term_freq_docId ON term_freq(docId)
    """)
    
    conn.commit()
    conn.close()
