"""
indexer.py — Document ingestion, incremental reindexing, BM25 stat builder.

Key design decisions (sheets 14, 17, 21):
  - Incremental reindex via (fileSize, fileMtime) fingerprint: unchanged
    files are skipped in O(1) time.
  - One SQLite transaction per file: a crash or full-disk mid-ingest
    rolls back only that file, not the whole batch.
  - term_freq populated per-chunk during ingest.
  - term_df rebuilt in a single SQL GROUP BY after each batch (cheap for
    desktop libraries; rebuild only on change).
  - FTS5 kept in sync via triggers defined in schema.py.
  - OCR is opt-in: caller sets ocr=True for a specific file.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Callable

from src.index.schema import get_db_connection, initialize_db, DB_PATH
from src.core import pdf_parser, epub_parser, chunker
from src.core.tokenizer import tokenize_words
from src.search.stemmer import stem_words
from src.utils import file_hash
from src.utils.constants import SEARCH_HISTORY_MAX


# ── Metadata helpers ──────────────────────────────────────────────────────────
_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20[0-2]\d)\b")


def _guess_year(file_path: str, pages: list) -> str:
    """
    Try to extract a 4-digit year from:
      1. The filename.
      2. First-page text.
    Returns empty string if not found.
    """
    m = _YEAR_RE.search(os.path.basename(file_path))
    if m:
        return m.group(1)
    if pages:
        m = _YEAR_RE.search(pages[0].text[:500])
        if m:
            return m.group(1)
    return ""


def _infer_file_type(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip(".")


# ── Core ingest function ──────────────────────────────────────────────────────
def index_file(
    file_path: str,
    db_path: str = DB_PATH,
    ocr: bool = False,
    progress_cb: Callable[[str, int, int], None] | None = None,
    force: bool = False,
) -> dict:
    """
    Index a single PDF or EPUB file.

    Parameters
    ----------
    file_path   : Absolute path to the file.
    db_path     : Override the database path (useful for testing).
    ocr         : Use Tesseract for scanned PDFs.
    progress_cb : Called as progress_cb(status_msg, current_page, total_pages).
    force       : Re-index even if fingerprint matches.

    Returns
    -------
    dict with keys: status ('skipped'|'indexed'|'failed'), message, chunk_count.
    """
    if not os.path.exists(file_path):
        return {"status": "failed", "message": f"File not found: {file_path}", "chunk_count": 0}

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".pdf", ".epub"):
        return {"status": "failed", "message": f"Unsupported format: {ext}", "chunk_count": 0}

    size, mtime = file_hash.doc_fingerprint(file_path)
    did = file_hash.doc_id(file_path)

    conn = get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT fileSize, fileMtime FROM documents WHERE id = ?", (did,)
        ).fetchone()

        if row and not force:
            if row["fileSize"] == size and abs(row["fileMtime"] - mtime) < 0.01:
                return {"status": "skipped", "message": "Already up to date.", "chunk_count": 0}

        # Remove stale data for this document
        if row:
            _delete_document(conn, did)

        # ── Extract text ──────────────────────────────────────────────────
        def _progress(msg, cur, tot):
            if progress_cb:
                progress_cb(msg, cur, tot)

        if ext == ".pdf":
            _progress("Extracting PDF text…", 0, 1)
            pages, err = pdf_parser.extract_pages(
                file_path,
                ocr=ocr,
                progress_cb=lambda c, t: _progress("OCR page…", c, t),
            )
        else:  # .epub
            _progress("Extracting EPUB text…", 0, 1)
            pages, err = epub_parser.extract_pages(file_path)

        if err:
            return {"status": "failed", "message": err, "chunk_count": 0}
        if not pages:
            return {"status": "failed", "message": "No text extracted.", "chunk_count": 0}

        # ── Chunk ─────────────────────────────────────────────────────────
        _progress("Chunking…", 0, 1)
        chunks = chunker.chunk_document(pages, file_path, did)

        # ── Write in a single transaction ─────────────────────────────────
        title = os.path.splitext(os.path.basename(file_path))[0]
        year = _guess_year(file_path, pages)
        total_tokens = sum(c.token_count for c in chunks)

        with conn:  # BEGIN / COMMIT / ROLLBACK
            conn.execute(
                """
                INSERT INTO documents
                    (id, title, filePath, pageCount, fileSize, fileType,
                     fileMtime, totalTokens, year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (did, title, file_path, len(pages), size,
                 _infer_file_type(file_path), mtime, total_tokens, year),
            )

            # Insert chunks + build per-chunk term frequencies
            for ch in chunks:
                conn.execute(
                    """
                    INSERT INTO pages_chunks
                        (id, docId, pageNum, chunkId, content, sectionHeader,
                         startChar, endChar, tokenCount, prevId, nextId)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ch.chunk_id, did, ch.page_num, ch.chunk_id,
                        ch.content, ch.section_header,
                        ch.start_char, ch.end_char, ch.token_count,
                        ch.prev_id or None, ch.next_id or None,
                    ),
                )

                # Compute stemmed term frequencies for this chunk
                words = tokenize_words(ch.content)
                stemmed = stem_words(words)
                tf_counter = Counter(stemmed)
                conn.executemany(
                    "INSERT OR IGNORE INTO term_freq(chunkId, docId, term, tf) VALUES (?, ?, ?, ?)",
                    [(ch.chunk_id, did, term, freq) for term, freq in tf_counter.items()],
                )

        _progress("Done.", len(chunks), len(chunks))
        return {"status": "indexed", "message": "OK", "chunk_count": len(chunks)}

    finally:
        conn.close()


def _delete_document(conn, doc_id: str) -> None:
    """Remove all rows for a document. Cascades to chunks + term_freq."""
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ── Batch ingest ──────────────────────────────────────────────────────────────
def index_paths(
    paths: list[str],
    db_path: str = DB_PATH,
    ocr: bool = False,
    progress_cb: Callable[[str, int, int, int, int], None] | None = None,
    force: bool = False,
) -> dict:
    """
    Index a list of file paths.

    progress_cb(file_path, file_index, file_total, page, page_total)
    Returns summary dict: {indexed, skipped, failed, errors}.
    """
    result = {"indexed": 0, "skipped": 0, "failed": 0, "errors": []}
    total = len(paths)

    for i, path in enumerate(paths, start=1):
        def _cb(msg, cur, tot, _path=path, _i=i):
            if progress_cb:
                progress_cb(_path, _i, total, cur, tot)

        r = index_file(path, db_path=db_path, ocr=ocr, progress_cb=_cb, force=force)
        if r["status"] == "indexed":
            result["indexed"] += 1
        elif r["status"] == "skipped":
            result["skipped"] += 1
        else:
            result["failed"] += 1
            result["errors"].append(f"{os.path.basename(path)}: {r['message']}")

    # Rebuild corpus-wide doc frequencies after the whole batch
    rebuild_term_df(db_path)
    return result


# ── BM25 stat maintenance ─────────────────────────────────────────────────────
def rebuild_term_df(db_path: str = DB_PATH) -> None:
    """
    Rebuild the term_df table from term_freq in one SQL statement.
    Called once at the end of each batch ingest.
    Acceptable for desktop libraries (< ~100k chunks).
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM term_df")
            conn.execute(
                """
                INSERT INTO term_df(term, df)
                SELECT term, COUNT(DISTINCT docId)
                FROM term_freq
                GROUP BY term
                """
            )
    finally:
        conn.close()


# ── Library listing ───────────────────────────────────────────────────────────
def list_documents(db_path: str = DB_PATH) -> list[dict]:
    """Return a list of all indexed documents as plain dicts."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, title, filePath, pageCount, indexedAt,
                   fileSize, author, year, language, fileType,
                   collection, totalTokens
            FROM documents
            ORDER BY indexedAt DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_document(doc_id: str, db_path: str = DB_PATH) -> None:
    """Remove a document and all its chunks from the index."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            _delete_document(conn, doc_id)
        rebuild_term_df(db_path)
    finally:
        conn.close()


# ── Search history helpers ────────────────────────────────────────────────────
def save_search_history(query: str, db_path: str = DB_PATH) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO search_history(query) VALUES (?)", (query,)
            )
            # Keep only the last N queries
            conn.execute(
                """
                DELETE FROM search_history
                WHERE id NOT IN (
                    SELECT id FROM search_history
                    ORDER BY searchedAt DESC
                    LIMIT ?
                )
                """,
                (SEARCH_HISTORY_MAX,),
            )
    finally:
        conn.close()


def get_search_history(db_path: str = DB_PATH) -> list[str]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT query FROM search_history ORDER BY searchedAt DESC"
        ).fetchall()
        return [r["query"] for r in rows]
    finally:
        conn.close()


# ── DB initialisation wrapper ─────────────────────────────────────────────────
def ensure_db(db_path: str = DB_PATH) -> None:
    """Create the database and schema if they do not exist yet."""
    initialize_db(db_path)
