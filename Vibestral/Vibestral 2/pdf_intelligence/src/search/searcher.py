# src/search/searcher.py
# Changes: Fixed mojibake ellipsis chars in _make_snippet; BM25 uses chunk-level
# CorpusStats (n_chunks, avg chunk tokens) not document-level; added intent to
# SearchResponse; kept Lovable's two-phase pipeline structure.
"""Two-phase searcher (sheet 21).

Phase 1 -- candidate generation
    SQLite FTS5 MATCH against chunks_fts. Returns up to CANDIDATE_LIMIT chunk
    rowids ranked by FTS bm25() (cheap, fast, approximate).

Phase 2 -- BM25 rerank
    Pull each candidate's stemmed term frequencies from term_freq, look up
    document frequencies in term_df, score with pure-Python BM25 at CHUNK level.
    Add small additive boost for synonym hits. Min-max normalize final scores.
    Optional rapidfuzz fuzzy fallback when no candidates found (typo tolerance).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..utils.constants import CANDIDATE_LIMIT, DEFAULT_RESULT_LIMIT, SYNONYM_BOOST
from . import bm25, query_parser
from .facets import facets_for_docs

log = logging.getLogger(__name__)

# Cache corpus stats to avoid recomputing on every query
_corpus_stats_cache: Optional[tuple[bm25.CorpusStats, float]] = None  # (stats, timestamp)


def _get_corpus_stats(conn: sqlite3.Connection) -> bm25.CorpusStats:
    """Get corpus stats with 60s cache to avoid recomputing on every query."""
    global _corpus_stats_cache
    now = time.time()
    if _corpus_stats_cache and (now - _corpus_stats_cache[1]) < 60:
        return _corpus_stats_cache[0]
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(AVG(token_count), 0) FROM pages_chunks"
    ).fetchone()
    stats = bm25.CorpusStats(
        n_chunks=int(row[0] or 0),
        avg_dl=float(row[1] or 0.0),
    )
    _corpus_stats_cache = (stats, now)
    return stats


@dataclass
class SearchResult:
    chunk_id: str
    doc_id: int
    title: str
    file_path: str
    file_type: str
    page_num: int
    section: Optional[str]
    snippet: str
    score: float
    author: Optional[str] = None
    year: Optional[int] = None


@dataclass
class SearchResponse:
    query: str
    results: List[SearchResult]
    facets: Dict[str, List[tuple[str, int]]]
    elapsed_ms: float
    intent: str = "general"
    used_fallback: bool = False
    total_candidates: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fetch_candidates(
    conn: sqlite3.Connection,
    fts_query: str,
    limit: int,
    filters: Optional[Dict[str, str]] = None,
    doc_ids: Optional[Sequence[int]] = None,
) -> List[sqlite3.Row]:
    where = ["chunks_fts MATCH ?"]
    params: list = [fts_query]
    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        where.append(f"d.id IN ({placeholders})")
        params.extend(doc_ids)
    if filters:
        for col in ("file_type", "author", "collection"):
            v = filters.get(col)
            if v:
                where.append(f"d.{col} = ?")
                params.append(v)
        if filters.get("year"):
            where.append("d.year = ?")
            params.append(int(filters["year"]))
    sql = f"""
        SELECT c.id, c.doc_id, c.page_num, c.section_header, c.content, c.token_count,
               d.title, d.file_path, d.file_type, d.author, d.year
        FROM chunks_fts f
        JOIN pages_chunks c ON c.rowid = f.rowid
        JOIN documents    d ON d.id    = c.doc_id
        WHERE {' AND '.join(where)}
        ORDER BY bm25(chunks_fts)
        LIMIT ?
    """
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def _df_lookup(conn: sqlite3.Connection, terms: Sequence[str]) -> Dict[str, int]:
    if not terms:
        return {}
    placeholders = ",".join("?" * len(terms))
    rows = conn.execute(
        f"SELECT term, df FROM term_df WHERE term IN ({placeholders})",
        tuple(terms),
    ).fetchall()
    return {t: int(df) for t, df in rows}


def _tf_lookup(
    conn: sqlite3.Connection,
    chunk_ids: Sequence[str],
    terms: Sequence[str],
) -> Dict[str, Dict[str, int]]:
    if not chunk_ids or not terms:
        return {}
    cph = ",".join("?" * len(chunk_ids))
    tph = ",".join("?" * len(terms))
    rows = conn.execute(
        f"""SELECT chunk_id, term, tf FROM term_freq
            WHERE chunk_id IN ({cph}) AND term IN ({tph})""",
        (*chunk_ids, *terms),
    ).fetchall()
    out: Dict[str, Dict[str, int]] = {}
    for cid, term, tf in rows:
        out.setdefault(cid, {})[term] = int(tf)
    return out


def _make_snippet(text: str, query_tokens: Sequence[str], width: int = 280) -> str:
    """Extract a relevant snippet centred on the first query term hit."""
    if not text:
        return ""
    lo = text.lower()
    hit = -1
    for tok in query_tokens:
        if not tok:
            continue
        idx = lo.find(tok.lower())
        if idx >= 0:
            hit = idx
            break
    if hit < 0:
        return (text[:width] + "\u2026") if len(text) > width else text
    start = max(0, hit - width // 3)
    end = min(len(text), start + width)
    snip = text[start:end]
    if start > 0:
        snip = "\u2026" + snip
    if end < len(text):
        snip = snip + "\u2026"
    return snip


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def search(
    conn: sqlite3.Connection,
    raw_query: str,
    *,
    limit: int = DEFAULT_RESULT_LIMIT,
    filters: Optional[Dict[str, str]] = None,
    doc_ids: Optional[Sequence[int]] = None,
) -> SearchResponse:
    t0 = time.perf_counter()
    pq = query_parser.parse(raw_query)
    if pq.is_empty():
        return SearchResponse(query=raw_query, results=[], facets={},
                              elapsed_ms=0.0, intent=pq.intent)

    # Phase 1: candidates
    candidates: List[sqlite3.Row] = []
    if pq.fts_query:
        try:
            candidates = _fetch_candidates(conn, pq.fts_query, CANDIDATE_LIMIT, filters, doc_ids)
        except sqlite3.OperationalError as e:
            log.warning("FTS query failed (%s); falling back to fuzzy scan", e)

    used_fallback = False
    if not candidates:
        candidates = _fuzzy_fallback(conn, pq.tokens, CANDIDATE_LIMIT, filters, doc_ids)
        used_fallback = bool(candidates)

    if not candidates:
        return SearchResponse(query=raw_query, results=[], facets={},
                              elapsed_ms=(time.perf_counter() - t0) * 1000,
                              intent=pq.intent)

    # Phase 2: BM25 rerank at CHUNK level
    stats = _get_corpus_stats(conn)

    all_terms = list(set(pq.stems) | pq.synonyms)
    df = _df_lookup(conn, all_terms)
    cids = [r[0] for r in candidates]
    tf = _tf_lookup(conn, cids, all_terms)

    scored: List[tuple[float, sqlite3.Row]] = []
    for r in candidates:
        cid = r[0]
        tok_count = r[5]
        tf_chunk = tf.get(cid, {})
        primary = bm25.score_chunk(
            query_terms=pq.stems, tf_in_chunk=tf_chunk,
            chunk_len=int(tok_count or 0), df_lookup=df, stats=stats,
        )
        if pq.synonyms:
            syn_score = bm25.score_chunk(
                query_terms=list(pq.synonyms), tf_in_chunk=tf_chunk,
                chunk_len=int(tok_count or 0), df_lookup=df, stats=stats,
            )
            primary += SYNONYM_BOOST * syn_score
        scored.append((primary, r))

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:limit]
    norm = bm25.normalize([s for s, _ in top])

    results: List[SearchResult] = []
    for (_, r), n in zip(top, norm):
        cid, doc_id, page_num, section, content, _, title, file_path, file_type, author, year = r
        snip = _make_snippet(content, pq.tokens + list(pq.phrases))
        results.append(SearchResult(
            chunk_id=cid, doc_id=int(doc_id), title=title,
            file_path=file_path, file_type=file_type,
            page_num=int(page_num), section=section,
            snippet=snip, score=round(float(n), 4),
            author=author, year=year,
        ))

    facet_doc_ids = list({r.doc_id for r in results})
    facets = facets_for_docs(conn, facet_doc_ids)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    _record_history(conn, raw_query)
    return SearchResponse(
        query=raw_query, results=results, facets=facets,
        elapsed_ms=round(elapsed_ms, 2), intent=pq.intent,
        used_fallback=used_fallback, total_candidates=len(candidates),
    )


def _fuzzy_fallback(
    conn: sqlite3.Connection,
    tokens: Sequence[str],
    limit: int,
    filters: Optional[Dict[str, str]],
    doc_ids: Optional[Sequence[int]] = None,
) -> List[sqlite3.Row]:
    """Used when FTS finds nothing -- likely a typo. rapidfuzz optional."""
    if not tokens:
        return []
    try:
        from rapidfuzz import fuzz  # type: ignore
        where = []
        params = []
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            where.append(f"d.id IN ({placeholders})")
            params.extend(doc_ids)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"""SELECT c.id, c.doc_id, c.page_num, c.section_header, c.content,
                      c.token_count, d.title, d.file_path, d.file_type, d.author, d.year
               FROM pages_chunks c JOIN documents d ON d.id = c.doc_id
               {where_clause}
               LIMIT 5000""",
            params,
        ).fetchall()
        needle = " ".join(tokens)
        scored = sorted(rows, key=lambda r: fuzz.partial_ratio(needle, r[4][:400]),
                        reverse=True)
        return scored[:limit]
    except ImportError:
        like = "%" + tokens[0] + "%"
        where = ["c.content LIKE ?"]
        params = [like]
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            where.append(f"d.id IN ({placeholders})")
            params.extend(doc_ids)
        params.append(limit)
        return conn.execute(
            f"""SELECT c.id, c.doc_id, c.page_num, c.section_header, c.content,
                      c.token_count, d.title, d.file_path, d.file_type, d.author, d.year
               FROM pages_chunks c JOIN documents d ON d.id = c.doc_id
               WHERE {' AND '.join(where)} LIMIT ?""",
            params,
        ).fetchall()


def _record_history(conn: sqlite3.Connection, q: str) -> None:
    try:
        conn.execute(
            "INSERT INTO search_history(query, created_at) VALUES (?, ?)",
            (q, time.time()),
        )
        conn.execute(
            """DELETE FROM search_history WHERE id NOT IN
               (SELECT id FROM search_history ORDER BY id DESC LIMIT 200)"""
        )
    except Exception:
        pass


def history(conn: sqlite3.Connection, limit: int = 20) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT query FROM search_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r[0] for r in rows]
