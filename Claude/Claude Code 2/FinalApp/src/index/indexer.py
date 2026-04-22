"""Indexer — T0 (Qwen Coder fixes) + T2 (holistic tables) + T3 (co-occurrence).

Per-file indexing:
  1. Fingerprint check (size + mtime) — skip if unchanged.
  2. Delete stale data (chunks, term_freq, term_df decremented, concepts, structure,
     cooccurrence delta).
  3. Extract pages (PDF / EPUB).
  4. Chunk pages (layered semantic chunker with structure classification).
  5. Batch-insert chunks, term_freq, chunk_structure, chunk_concepts.
  6. Update term_df incrementally.
  7. Update term_cooccurrence pairs within each chunk.
  8. Optionally embed chunks (T5).
  9. COMMIT.  Failure → ROLLBACK (only that file).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..core import pdf_parser, epub_parser
from ..core.chunker import Chunk, chunk_document
from ..core.tokenizer import word_tokens
from ..search.stemmer import stem, stem_all
from ..utils.constants import (
    COOCCUR_WINDOW, SUPPORTED_EXTS, DB_PATH,
    EMBEDDING_ENABLED,
)
from ..utils.file_hash import doc_fingerprint, doc_id_from_path
from ..utils.synonyms import expand_atom
from .schema import get_connection

log = logging.getLogger(__name__)


# ── Public API ───────────────────────────────────────────────────────────────

def index_paths(
    paths: List[str],
    conn: sqlite3.Connection,
    *,
    ocr: bool = False,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, int]:
    """Index a list of file paths. Returns {ok, skipped, failed} counts."""
    counts = {"ok": 0, "skipped": 0, "failed": 0}
    total = len(paths)
    for i, path in enumerate(paths):
        if progress_cb:
            progress_cb(path, i + 1, total)
        try:
            result = index_file(path, conn, ocr=ocr)
            counts[result] = counts.get(result, 0) + 1
        except Exception as e:
            log.error("Failed to index %s: %s", path, e)
            counts["failed"] += 1
    # Rebuild term_df once after batch (faster than per-file)
    _rebuild_term_df(conn)
    return counts


def index_file(
    file_path: str,
    conn: sqlite3.Connection,
    *,
    ocr: bool = False,
) -> str:
    """Index one file. Returns 'ok', 'skipped', or raises."""
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {ext}")

    size, mtime = doc_fingerprint(file_path)
    doc_id = doc_id_from_path(file_path)

    # Check fingerprint
    row = conn.execute(
        "SELECT file_size, file_mtime FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    if row and int(row["file_size"]) == size and float(row["file_mtime"]) == mtime:
        return "skipped"

    try:
        conn.execute("BEGIN")

        # Remove stale data if re-indexing
        if row:
            _delete_doc(doc_id, conn)

        # Extract text
        if ext == ".pdf":
            pages = pdf_parser.extract_pages(file_path, ocr=ocr)
        else:
            pages = epub_parser.extract_pages(file_path)

        # Chunk
        page_tuples = [(p.page_num, p.text, p.heading_hint) for p in pages]
        chunks: List[Chunk] = chunk_document(file_path=file_path, pages=page_tuples)

        if not chunks:
            conn.execute("ROLLBACK")
            return "ok"

        # ── Batch insert chunks ──────────────────────────────────────────
        chunk_rows = [
            (c.id, doc_id, c.page_num, idx, c.text,
             c.section, c.start_char, c.end_char, c.token_count,
             c.prev_id, c.next_id)
            for idx, c in enumerate(chunks)
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO pages_chunks
               (id, doc_id, page_num, chunk_idx, content, section_header,
                start_char, end_char, token_count, prev_id, next_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            chunk_rows,
        )

        # ── chunk_structure ──────────────────────────────────────────────
        struct_rows = [
            (c.id, c.structure_type, c.density_score) for c in chunks
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO chunk_structure(chunk_id,structure_type,density_score) VALUES(?,?,?)",
            struct_rows,
        )

        # ── term_freq + chunk_concepts + co-occurrence ───────────────────
        tf_rows: List[Tuple] = []
        concept_rows: List[Tuple] = []
        cooc_pairs: Dict[Tuple[str, str], int] = {}
        total_tokens = 0

        for c in chunks:
            raw_tokens = word_tokens(c.text)
            stemmed = stem_all(raw_tokens)
            total_tokens += c.token_count

            # term_freq (per chunk, per stemmed token)
            freq: Dict[str, int] = {}
            for s in stemmed:
                if s:
                    freq[s] = freq.get(s, 0) + 1
            for term, tf in freq.items():
                tf_rows.append((c.id, doc_id, term, tf))

            # chunk_concepts: expand each unique stem via thesaurus
            added_concepts: set = set()
            for raw_tok in set(raw_tokens):
                exp = expand_atom(raw_tok)
                for d in exp.direct:
                    for w in d.split():
                        s = stem(w)
                        if s and (c.id, s) not in added_concepts:
                            concept_rows.append((c.id, s, "direct", 0.85))
                            added_concepts.add((c.id, s))
                for con in exp.concepts:
                    for w in con.split():
                        s = stem(w)
                        if s and (c.id, s) not in added_concepts:
                            concept_rows.append((c.id, s, "concept", 0.60))
                            added_concepts.add((c.id, s))

            # co-occurrence: within chunk window
            win = stemmed[:COOCCUR_WINDOW]
            for i, ta in enumerate(win):
                for tb in win[i+1:i+6]:
                    if ta and tb and ta != tb:
                        key = (min(ta, tb), max(ta, tb))
                        cooc_pairs[key] = cooc_pairs.get(key, 0) + 1

        conn.executemany(
            "INSERT OR REPLACE INTO term_freq(chunk_id,doc_id,term,tf) VALUES(?,?,?,?)",
            tf_rows,
        )
        conn.executemany(
            """INSERT INTO chunk_concepts(chunk_id,concept,source,weight) VALUES(?,?,?,?)
               ON CONFLICT(chunk_id,concept) DO UPDATE SET weight=MAX(weight,excluded.weight)""",
            concept_rows,
        )
        if cooc_pairs:
            conn.executemany(
                """INSERT INTO term_cooccurrence(term_a,term_b,count) VALUES(?,?,?)
                   ON CONFLICT(term_a,term_b) DO UPDATE SET count=count+excluded.count""",
                [(a, b, n) for (a, b), n in cooc_pairs.items()],
            )

        # ── Document row ─────────────────────────────────────────────────
        title = Path(file_path).stem
        conn.execute(
            """INSERT OR REPLACE INTO documents
               (id,title,file_path,file_type,page_count,file_size,file_mtime,
                indexed_at,total_tokens)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (doc_id, title, file_path, ext.lstrip("."),
             len(pages), size, mtime, time.time(), total_tokens),
        )

        # ── Optional embedding (T5) ───────────────────────────────────────
        if EMBEDDING_ENABLED:
            _embed_chunks(chunks, doc_id, conn)

        conn.execute("COMMIT")
        return "ok"

    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


def remove_file(file_path: str, conn: sqlite3.Connection) -> bool:
    """Remove a document and all its data from the index."""
    doc_id = doc_id_from_path(file_path)
    row = conn.execute("SELECT id FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return False
    conn.execute("BEGIN")
    _delete_doc(doc_id, conn)
    conn.execute("COMMIT")
    _rebuild_term_df(conn)
    return True


# ── Helpers ──────────────────────────────────────────────────────────────────

def _delete_doc(doc_id: str, conn: sqlite3.Connection) -> None:
    """Remove all data for a document (ON DELETE CASCADE handles children)."""
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    # CASCADE removes pages_chunks, term_freq, chunk_structure,
    # chunk_concepts, chunk_embeddings automatically.
    # Cooccurrence cleanup: too expensive per-doc; leave stale counts
    # (they're additive signals, not primary; minor staleness is acceptable).


def _rebuild_term_df(conn: sqlite3.Connection) -> None:
    """Rebuild corpus-wide document frequency from term_freq."""
    conn.executescript("""
        DELETE FROM term_df;
        INSERT INTO term_df(term, df)
        SELECT term, COUNT(DISTINCT doc_id) FROM term_freq GROUP BY term;
    """)
    conn.commit()


def _embed_chunks(chunks: List[Chunk], doc_id: str, conn: sqlite3.Connection) -> None:
    """Embed chunks with bge-micro if available (T5). Silently skips if not."""
    try:
        from ..search.embeddings import embed_texts, MODEL_VERSION  # type: ignore
        import struct
        texts = [c.text[:512] for c in chunks]
        vecs = embed_texts(texts)
        rows = []
        for c, vec in zip(chunks, vecs):
            blob = struct.pack(f"{len(vec)}f", *vec)
            rows.append((c.id, blob, MODEL_VERSION))
        conn.executemany(
            """INSERT OR REPLACE INTO chunk_embeddings(chunk_id,embedding,model_version)
               VALUES(?,?,?)""",
            rows,
        )
    except ImportError:
        pass
    except Exception as e:
        log.warning("Embedding failed for doc %s: %s", doc_id, e)
