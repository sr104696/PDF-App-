"""Indexer: ingest PDF/EPUB → SQLite + FTS5 + BM25 stats.

Incremental reindex (offline-search pattern):
  Skip a file if (file_size, file_mtime) match the stored fingerprint.
  Otherwise delete its rows and re-ingest. This avoids hashing GB of PDFs
  on every library scan.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Optional

from ..core import pdf_parser, epub_parser
from ..core.chunker import chunk_document, Chunk
from ..core.tokenizer import word_tokens
from ..search.stemmer import stem_all
from ..utils.constants import SUPPORTED_EXTS
from ..utils.file_hash import doc_fingerprint

log = logging.getLogger(__name__)
ProgressCb = Optional[Callable[[str, int, int], None]]   # (msg, done, total)


# ---------- helpers ----------------------------------------------------
def _file_type(path: Path) -> str:
    return "pdf" if path.suffix.lower() == ".pdf" else "epub"


def _pages_for(path: Path, ocr: bool) -> Iterable[tuple[int, str, Optional[str]]]:
    if path.suffix.lower() == ".pdf":
        for p in pdf_parser.extract_pages(path, ocr=ocr):
            yield p.page_num, p.text, p.heading
    else:
        for ch in epub_parser.extract_chapters(path):
            yield ch.page_num, ch.text, ch.heading


def _existing_fingerprint(conn: sqlite3.Connection, path: str):
    row = conn.execute(
        "SELECT id, file_size, file_mtime FROM documents WHERE file_path = ?",
        (path,),
    ).fetchone()
    return row  # (id, size, mtime) or None


def _delete_doc(conn: sqlite3.Connection, doc_id: int) -> None:
    # ON DELETE CASCADE handles pages_chunks → term_freq.
    # We must rebuild term_df after a removal; caller is responsible.
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ---------- public API -------------------------------------------------
def index_paths(
    conn: sqlite3.Connection,
    paths: Iterable[Path],
    *,
    ocr: bool = False,
    progress: ProgressCb = None,
) -> dict:
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(
                f for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
            )
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)

    total = len(files)
    indexed = skipped = failed = 0
    for i, path in enumerate(files, start=1):
        if progress:
            progress(f"Indexing {path.name}", i - 1, total)
        try:
            status = index_file(conn, path, ocr=ocr)
            if status == "indexed":
                indexed += 1
            elif status == "skipped":
                skipped += 1
        except Exception as e:
            log.exception("Failed to index %s: %s", path, e)
            failed += 1

    rebuild_term_df(conn)
    if progress:
        progress("Done", total, total)
    return {"total": total, "indexed": indexed, "skipped": skipped, "failed": failed}


def index_file(conn: sqlite3.Connection, path: Path, *, ocr: bool = False) -> str:
    path = path.resolve()
    if not path.exists():
        return "missing"
    if path.suffix.lower() not in SUPPORTED_EXTS:
        return "unsupported"

    size, mtime = doc_fingerprint(path)
    existing = _existing_fingerprint(conn, str(path))
    if existing and existing[1] == size and abs(existing[2] - mtime) < 1e-6:
        return "skipped"

    # Replace any prior version of this file.
    if existing:
        _delete_doc(conn, existing[0])

    file_type = _file_type(path)
    title = path.stem
    page_count = (
        pdf_parser.page_count(path) if file_type == "pdf"
        else epub_parser.chapter_count(path)
    )

    conn.execute("BEGIN")
    try:
        cur = conn.execute(
            """INSERT INTO documents
               (title, file_path, file_type, page_count, file_size, file_mtime,
                indexed_at, total_tokens)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            (title, str(path), file_type, page_count, size, mtime, time.time()),
        )
        doc_id = cur.lastrowid

        chunks = chunk_document(file_path=str(path), pages=_pages_for(path, ocr=ocr))
        total_tokens = 0
        for idx, ch in enumerate(chunks):
            _insert_chunk(conn, doc_id, idx, ch)
            total_tokens += ch.token_count

        conn.execute(
            "UPDATE documents SET total_tokens = ? WHERE id = ?",
            (total_tokens, doc_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return "indexed"


def _insert_chunk(conn: sqlite3.Connection, doc_id: int, idx: int, ch: Chunk) -> None:
    conn.execute(
        """INSERT INTO pages_chunks
           (id, doc_id, page_num, chunk_idx, content, section_header,
            start_char, end_char, token_count, prev_id, next_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ch.id, doc_id, ch.page_num, idx, ch.text, ch.section,
         ch.start_char, ch.end_char, ch.token_count, ch.prev_id, ch.next_id),
    )
    stems = stem_all(word_tokens(ch.text))
    if stems:
        counts = Counter(stems)
        conn.executemany(
            "INSERT OR REPLACE INTO term_freq (chunk_id, term, tf) VALUES (?, ?, ?)",
            [(ch.id, term, tf) for term, tf in counts.items()],
        )


def rebuild_term_df(conn: sqlite3.Connection) -> None:
    """Recompute corpus-wide document frequency. Cheap on small/medium libraries."""
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM term_df")
        conn.execute(
            """INSERT INTO term_df (term, df)
               SELECT term, COUNT(DISTINCT chunk_id) FROM term_freq GROUP BY term"""
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def remove_document(conn: sqlite3.Connection, doc_id: int) -> None:
    _delete_doc(conn, doc_id)
    rebuild_term_df(conn)


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT id, title, file_path, file_type, page_count, total_tokens,
                  indexed_at, file_size, collection, author, year
           FROM documents ORDER BY title COLLATE NOCASE"""
    ).fetchall()
    cols = ["id", "title", "file_path", "file_type", "page_count", "total_tokens",
            "indexed_at", "file_size", "collection", "author", "year"]
    return [dict(zip(cols, r)) for r in rows]


def corpus_stats(conn: sqlite3.Connection) -> tuple[int, float]:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(AVG(token_count), 0) FROM pages_chunks"
    ).fetchone()
    return int(row[0] or 0), float(row[1] or 0.0)
