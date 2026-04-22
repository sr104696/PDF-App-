"""
searcher.py — Two-phase search pipeline (sheet 21, steps 1-10).

Phase 1 — Candidate generation:
  SQLite FTS5 MATCH with the parsed FTS expression.
  Capped at CANDIDATE_LIMIT (200) rows, ordered by FTS5's built-in BM25.

Phase 2 — Rerank:
  Our pure-Python Okapi BM25 (bm25.py) re-scores the candidates using
  pre-stored term_freq / term_df stats.
  Synonym hits get a small additive boost (SYNONYM_BOOST).
  Scores are min-max normalised to [0, 1].

Fallback:
  If FTS5 returns 0 results (e.g. a badly typed query), we try rapidfuzz
  fuzzy matching over a bounded slice of all chunks (max 5 000 rows).
  If rapidfuzz isn't installed, we degrade to a SQL LIKE scan.

Result format:
  Each SearchResult includes: title, file_path, page_num, section_header,
  snippet (±context), score, author, year, file_type.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass

from src.search.query_parser import parse, ParsedQuery
from src.search.bm25 import score_chunks, min_max_normalize
from src.search.facets import facets_for_docs
from src.index.schema import get_db_connection, DB_PATH
from src.index.indexer import save_search_history
from src.utils.constants import CANDIDATE_LIMIT, TOP_K_DEFAULT

# Optional rapidfuzz for typo fallback
try:
    from rapidfuzz import fuzz as _fuzz, process as _rfprocess
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


@dataclass
class SearchResult:
    chunk_id: str
    doc_id: str
    title: str
    file_path: str
    page_num: int
    section_header: str
    snippet: str
    score: float            # normalised [0, 1]
    author: str
    year: str
    file_type: str


@dataclass
class SearchResponse:
    results: list[SearchResult]
    facets: dict
    query_intent: str
    total_candidates: int
    used_fallback: bool = False


def _build_snippet(content: str, query_terms: list[str], max_len: int = 300) -> str:
    """
    Extract a relevant snippet from *content* centred on the first query
    term hit.  Falls back to the first max_len characters.
    """
    lower = content.lower()
    best_pos = len(content)
    for term in query_terms:
        pos = lower.find(term.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos

    if best_pos == len(content):
        # No term found; return start
        return content[:max_len].strip() + ("…" if len(content) > max_len else "")

    start = max(0, best_pos - 80)
    end = start + max_len
    snippet = content[start:end].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return prefix + snippet + suffix


def _fuzzy_fallback(
    raw_query: str,
    db_path: str,
    limit: int = 10,
) -> list[dict]:
    """
    Fallback when FTS returns nothing.  Two modes:
      1. rapidfuzz partial_ratio over a bounded slice.
      2. SQL LIKE scan (slower but always available).
    """
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT pc.id AS chunk_id, pc.docId, pc.pageNum,
                   pc.content, pc.sectionHeader,
                   d.title, d.filePath, d.author, d.year, d.fileType
            FROM pages_chunks pc
            JOIN documents d ON pc.docId = d.id
            LIMIT 5000
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    if _HAS_RAPIDFUZZ:
        contents = [r["content"] for r in rows]
        matches = _rfprocess.extract(
            raw_query, contents, scorer=_fuzz.partial_ratio, limit=limit
        )
        result_rows = []
        for _text, score, idx in matches:
            if score >= 40:
                r = rows[idx]
                result_rows.append({**dict(r), "bm25_score": score / 100.0})
        return result_rows

    # SQL LIKE fallback
    conn = get_db_connection(db_path)
    try:
        tokens = raw_query.lower().split()
        like_clause = " OR ".join(
            f"LOWER(pc.content) LIKE ?" for _ in tokens
        )
        params = [f"%{t}%" for t in tokens]
        rows2 = conn.execute(
            f"""
            SELECT pc.id AS chunk_id, pc.docId, pc.pageNum,
                   pc.content, pc.sectionHeader,
                   d.title, d.filePath, d.author, d.year, d.fileType
            FROM pages_chunks pc
            JOIN documents d ON pc.docId = d.id
            WHERE {like_clause}
            LIMIT {limit}
            """,
            params,
        ).fetchall()
        return [{**dict(r), "bm25_score": 0.5} for r in rows2]
    finally:
        conn.close()


def search(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    filters: dict | None = None,
    db_path: str = DB_PATH,
    save_history: bool = True,
) -> SearchResponse:
    """
    Execute the two-phase search pipeline.

    Parameters
    ----------
    query        : Raw user query string.
    top_k        : Maximum results to return.
    filters      : Optional facet filters, e.g. {'author': 'Arendt', 'year': '2000'}.
    db_path      : Database path.
    save_history : Persist the query in search_history table.

    Returns
    -------
    SearchResponse with results, facets, and diagnostics.
    """
    pq: ParsedQuery = parse(query)

    if pq.is_empty():
        return SearchResponse(results=[], facets={}, query_intent="general", total_candidates=0)

    if save_history:
        try:
            save_search_history(query, db_path)
        except Exception:
            pass

    conn = get_db_connection(db_path)
    used_fallback = False
    raw_rows: list = []

    try:
        # ── Phase 1: FTS5 candidate generation ───────────────────────────
        fts_expr = pq.fts_expression()
        if fts_expr:
            sql = """
                SELECT
                    pc.id            AS chunk_id,
                    pc.docId,
                    pc.pageNum,
                    pc.content,
                    pc.sectionHeader,
                    d.title,
                    d.filePath,
                    d.author,
                    d.year,
                    d.fileType
                FROM chunks_fts f
                JOIN pages_chunks pc ON f.rowid = pc.rowid
                JOIN documents   d  ON pc.docId = d.id
                WHERE chunks_fts MATCH ?
            """
            params: list = [fts_expr]

            # Apply facet pre-filters
            if filters:
                for key in ("author", "year", "fileType", "collection"):
                    val = filters.get(key)
                    if val:
                        sql += f" AND d.{key} = ?"
                        params.append(val)
                if filters.get("tag"):
                    sql += """
                        AND EXISTS (
                            SELECT 1 FROM doc_tags dt
                            WHERE dt.docId = d.id AND dt.tag = ?
                        )
                    """
                    params.append(filters["tag"])

            sql += f" ORDER BY rank LIMIT {CANDIDATE_LIMIT}"

            try:
                raw_rows = conn.execute(sql, params).fetchall()
            except Exception:
                raw_rows = []

    finally:
        conn.close()

    # ── Fallback for zero FTS hits ────────────────────────────────────────
    if not raw_rows:
        raw_rows_dicts = _fuzzy_fallback(query, db_path, limit=top_k)
        used_fallback = True
        # Build SearchResult objects directly from fuzzy output
        results: list[SearchResult] = []
        seen_docs: set[str] = set()
        for r in raw_rows_dicts:
            sr = SearchResult(
                chunk_id=r.get("chunk_id", ""),
                doc_id=r.get("docId", ""),
                title=r.get("title", ""),
                file_path=r.get("filePath", ""),
                page_num=r.get("pageNum", 0),
                section_header=r.get("sectionHeader", "") or "",
                snippet=_build_snippet(r.get("content", ""), pq.terms),
                score=r.get("bm25_score", 0.0),
                author=r.get("author", "") or "",
                year=r.get("year", "") or "",
                file_type=r.get("fileType", "") or "",
            )
            results.append(sr)
            seen_docs.add(sr.doc_id)

        facets = facets_for_docs(list(seen_docs), db_path)
        return SearchResponse(
            results=results[:top_k],
            facets=facets,
            query_intent=pq.intent,
            total_candidates=len(results),
            used_fallback=True,
        )

    # ── Phase 2: BM25 rerank ──────────────────────────────────────────────
    candidate_ids = [r["chunk_id"] for r in raw_rows]
    raw_scores = score_chunks(
        query_terms=pq.stemmed or pq.terms,
        candidate_chunk_ids=candidate_ids,
        synonym_terms=pq.synonyms,
        db_path=db_path,
    )
    normalised = min_max_normalize(raw_scores)

    # Build SearchResult list, sorted by score descending
    id_to_row = {r["chunk_id"]: r for r in raw_rows}
    results_unsorted: list[SearchResult] = []
    for cid, score in normalised.items():
        r = id_to_row.get(cid)
        if r is None:
            continue
        results_unsorted.append(SearchResult(
            chunk_id=cid,
            doc_id=r["docId"],
            title=r["title"],
            file_path=r["filePath"],
            page_num=r["pageNum"],
            section_header=r["sectionHeader"] or "",
            snippet=_build_snippet(r["content"], pq.terms + pq.stemmed),
            score=score,
            author=r["author"] or "",
            year=r["year"] or "",
            file_type=r["fileType"] or "",
        ))

    results_sorted = sorted(results_unsorted, key=lambda x: x.score, reverse=True)[:top_k]

    # Facet aggregation over the final doc set
    seen_docs = list({r.doc_id for r in results_sorted})
    facets = facets_for_docs(seen_docs, db_path)

    return SearchResponse(
        results=results_sorted,
        facets=facets,
        query_intent=pq.intent,
        total_candidates=len(raw_rows),
        used_fallback=used_fallback,
    )
