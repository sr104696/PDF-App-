"""Holistic searcher — all five tiers in one pipeline.

Phase 1  — Broad FTS5 candidate generation (stems + direct + concepts).
Phase 2  — Multi-signal BM25 composite scoring:
             BM25 on stems, direct synonyms, concept neighbors,
             corpus co-occurrence, structural intent bonus,
             proximity bonus, section-header bonus, embedding similarity.
Phase 3  — Coherence pass: Jaccard dedup + adjacency boost.
Fallback — rapidfuzz fuzzy search → double-metaphone phonetic fallback.
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..utils.constants import (
    CANDIDATE_LIMIT, DEFAULT_RESULT_LIMIT, COOCCUR_TOPK,
    W_STEM, W_SYN, W_CON, W_COOC, W_STRUCT, W_EMB, W_PROX, W_HDR,
    JACCARD_DUP_THRESH, EMBEDDING_ENABLED,
)
from . import bm25, query_parser
from .facets import facets_for_docs

log = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    chunk_id: str
    doc_id: str
    title: str
    file_path: str
    file_type: str
    page_num: int
    section: Optional[str]
    snippet: str
    score: float
    intent_labels: List[str] = field(default_factory=list)
    structure_type: str = "exposition"
    expansion_debug: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SearchResponse:
    query: str
    results: List[SearchResult]
    facets: Dict
    elapsed_ms: float
    intents: List[str] = field(default_factory=list)
    expansion_debug: Dict[str, list] = field(default_factory=dict)


# ── Candidate fetch ──────────────────────────────────────────────────────────

def _fetch_candidates(
    conn: sqlite3.Connection,
    fts_query: str,
    limit: int,
    filters: Optional[Dict[str, str]],
) -> List[sqlite3.Row]:
    where = ["chunks_fts MATCH ?"]
    params: list = [fts_query]
    if filters:
        for col in ("file_type", "author", "collection"):
            v = filters.get(col)
            if v:
                where.append(f"d.{col} = ?")
                params.append(v)
        if filters.get("year"):
            try:
                where.append("d.year = ?")
                params.append(int(filters["year"]))
            except ValueError:
                pass
    sql = f"""
        SELECT c.id, c.doc_id, c.page_num, c.section_header,
               c.content, c.token_count, c.prev_id, c.next_id,
               d.title, d.file_path, d.file_type
        FROM chunks_fts f
        JOIN pages_chunks c ON c.rowid = f.rowid
        JOIN documents    d ON d.id    = c.doc_id
        WHERE {' AND '.join(where)}
        ORDER BY bm25(chunks_fts)
        LIMIT ?
    """
    params.append(limit)
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        log.warning("FTS query error (%s) — query was: %s", e, fts_query)
        return []


# ── Lookup helpers ───────────────────────────────────────────────────────────

def _df_lookup(conn: sqlite3.Connection, terms: Sequence[str]) -> Dict[str, int]:
    if not terms:
        return {}
    ph = ",".join("?" * len(terms))
    rows = conn.execute(
        f"SELECT term, df FROM term_df WHERE term IN ({ph})", tuple(terms)
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


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


def _struct_lookup(
    conn: sqlite3.Connection, chunk_ids: Sequence[str]
) -> Dict[str, str]:
    if not chunk_ids:
        return {}
    ph = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT chunk_id, structure_type FROM chunk_structure WHERE chunk_id IN ({ph})",
        tuple(chunk_ids),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def _cooc_lookup(
    conn: sqlite3.Connection, stems: Sequence[str], topk: int = COOCCUR_TOPK
) -> List[str]:
    """Return top-K terms that co-occur most with the query stems in this corpus."""
    if not stems:
        return []
    ph = ",".join("?" * len(stems))
    rows = conn.execute(
        f"""SELECT term_b as partner, SUM(count) as total
            FROM term_cooccurrence WHERE term_a IN ({ph})
            GROUP BY term_b ORDER BY total DESC LIMIT ?""",
        (*tuple(stems), topk),
    ).fetchall()
    partners = [r[0] for r in rows]
    # Also check reverse direction
    rows2 = conn.execute(
        f"""SELECT term_a as partner, SUM(count) as total
            FROM term_cooccurrence WHERE term_b IN ({ph})
            GROUP BY term_a ORDER BY total DESC LIMIT ?""",
        (*tuple(stems), topk),
    ).fetchall()
    for r in rows2:
        if r[0] not in partners:
            partners.append(r[0])
    return partners[:topk]


def _embed_lookup(
    conn: sqlite3.Connection,
    chunk_ids: Sequence[str],
    query_vec: Optional[List[float]],
) -> Dict[str, float]:
    """Return cosine similarity scores for chunk_ids if embeddings available."""
    if not EMBEDDING_ENABLED or query_vec is None or not chunk_ids:
        return {}
    ph = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT chunk_id, embedding FROM chunk_embeddings WHERE chunk_id IN ({ph})",
        tuple(chunk_ids),
    ).fetchall()
    scores: Dict[str, float] = {}
    q_norm = math.sqrt(sum(x * x for x in query_vec)) or 1.0
    for cid, blob in rows:
        try:
            n = len(blob) // 4
            vec = struct.unpack(f"{n}f", blob)
            dot = sum(a * b for a, b in zip(query_vec, vec))
            v_norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            scores[cid] = dot / (q_norm * v_norm)
        except Exception:
            pass
    return scores


# ── Snippet builder ──────────────────────────────────────────────────────────

def _make_snippet(text: str, tokens: Sequence[str], width: int = 280) -> str:
    if not text:
        return ""
    lo = text.lower()
    hit = -1
    for tok in tokens:
        if not tok:
            continue
        idx = lo.find(tok.lower())
        if idx >= 0:
            hit = idx
            break
    if hit < 0:
        return (text[:width] + "…") if len(text) > width else text
    start = max(0, hit - width // 3)
    end = min(len(text), start + width)
    snip = text[start:end]
    if start > 0:
        snip = "…" + snip
    if end < len(text):
        snip += "…"
    return snip


# ── Jaccard dedup ────────────────────────────────────────────────────────────

def _token_set(text: str) -> Set[str]:
    return set(re.findall(r"\b[a-z]{2,}\b", text.lower()))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Fuzzy fallbacks ──────────────────────────────────────────────────────────

def _fuzzy_fallback(
    conn: sqlite3.Connection,
    tokens: Sequence[str],
    limit: int,
    filters: Optional[Dict],
) -> List[sqlite3.Row]:
    if not tokens:
        return []
    needle = " ".join(tokens)

    # 1. Try rapidfuzz
    try:
        from rapidfuzz import fuzz  # type: ignore
        rows = conn.execute(
            """SELECT c.id, c.doc_id, c.page_num, c.section_header,
                      c.content, c.token_count, c.prev_id, c.next_id,
                      d.title, d.file_path, d.file_type
               FROM pages_chunks c JOIN documents d ON d.id = c.doc_id
               LIMIT 5000"""
        ).fetchall()
        scored = sorted(rows, key=lambda r: fuzz.partial_ratio(needle, r[4][:400]), reverse=True)
        return scored[:limit]
    except ImportError:
        pass

    # 2. Phonetic double-metaphone fallback
    try:
        from .phonetic import double_metaphone_query  # type: ignore
        return double_metaphone_query(conn, tokens, limit)
    except ImportError:
        pass

    # 3. LIKE scan (always available)
    like = "%" + tokens[0] + "%"
    return conn.execute(
        """SELECT c.id, c.doc_id, c.page_num, c.section_header,
                  c.content, c.token_count, c.prev_id, c.next_id,
                  d.title, d.file_path, d.file_type
           FROM pages_chunks c JOIN documents d ON d.id = c.doc_id
           WHERE c.content LIKE ? LIMIT ?""",
        (like, limit),
    ).fetchall()


# ── Main search function ─────────────────────────────────────────────────────

def search(
    conn: sqlite3.Connection,
    raw_query: str,
    *,
    limit: int = DEFAULT_RESULT_LIMIT,
    filters: Optional[Dict[str, str]] = None,
) -> SearchResponse:
    t0 = time.perf_counter()
    pq = query_parser.parse(raw_query)
    if pq.is_empty():
        return SearchResponse(query=raw_query, results=[], facets={},
                              elapsed_ms=0.0, intents=pq.intents)

    # ── Corpus co-occurrence enrichment (T3) ────────────────────────────
    cooc_terms = _cooc_lookup(conn, pq.stems)
    pq.cooc_stems = cooc_terms

    # ── Phase 1: Candidate generation ───────────────────────────────────
    candidates: List[sqlite3.Row] = []
    if pq.fts_query:
        candidates = _fetch_candidates(conn, pq.fts_query, CANDIDATE_LIMIT, filters)

    if not candidates:
        candidates = _fuzzy_fallback(conn, pq.tokens, CANDIDATE_LIMIT, filters)

    if not candidates:
        return SearchResponse(
            query=raw_query, results=[], facets={},
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            intents=pq.intents,
        )

    # ── Phase 2: Multi-signal composite scoring ──────────────────────────
    n_row = conn.execute(
        "SELECT COUNT(*), COALESCE(AVG(token_count), 0) FROM pages_chunks"
    ).fetchone()
    stats = bm25.CorpusStats(
        n_docs=int(n_row[0] or 0),
        avg_dl=float(n_row[1] or 0.0),
    )

    all_terms = list(dict.fromkeys(
        pq.stems + pq.direct_stems + pq.concept_stems + cooc_terms
    ))
    df = _df_lookup(conn, all_terms)
    cids = [r[0] for r in candidates]
    tf = _tf_lookup(conn, cids, all_terms)
    struct_map = _struct_lookup(conn, cids)

    # Embedding query vector (T5)
    query_vec: Optional[List[float]] = None
    if EMBEDDING_ENABLED:
        try:
            from .embeddings import embed_texts  # type: ignore
            vecs = embed_texts([raw_query])
            query_vec = vecs[0] if vecs else None
        except Exception:
            pass
    embed_scores = _embed_lookup(conn, cids, query_vec)

    # Build set of chunk IDs that are adjacent to other candidates (proximity)
    prev_next_ids: Set[str] = set()
    for r in candidates:
        if r[6]:  # prev_id
            prev_next_ids.add(r[6])
        if r[7]:  # next_id
            prev_next_ids.add(r[7])

    # Header terms (for header bonus)
    header_stem_set = set(pq.stems)

    scored: List[Tuple[float, sqlite3.Row]] = []
    for r in candidates:
        cid, doc_id, page_num, section, content, tok_count, prev_id, next_id, title, fp, ftype = r
        tf_chunk = tf.get(cid, {})
        chunk_len = int(tok_count or 1)
        struct_type = struct_map.get(cid, "exposition")

        # Structural intent bonus
        struct_bonus = W_STRUCT if struct_type in pq.boosted_structures else 0.0

        # Proximity bonus — prev or next chunk is also in candidates
        prox_bonus = W_PROX if (prev_id in prev_next_ids or next_id in prev_next_ids) else 0.0

        # Header bonus
        header_bonus = 0.0
        if section:
            sec_tokens = set(re.findall(r"\b[a-z]{2,}\b", section.lower()))
            if sec_tokens & header_stem_set:
                header_bonus = W_HDR

        # Embedding score
        emb_score = embed_scores.get(cid, 0.0)

        composite = bm25.score_chunk(
            stem_terms=pq.stems,
            direct_terms=pq.direct_stems,
            concept_terms=pq.concept_stems,
            cooc_terms=cooc_terms,
            tf_in_chunk=tf_chunk,
            chunk_len=chunk_len,
            df_lookup=df,
            stats=stats,
            w_stem=W_STEM, w_syn=W_SYN, w_con=W_CON, w_cooc=W_COOC,
            struct_bonus=struct_bonus,
            prox_bonus=prox_bonus,
            header_bonus=header_bonus,
            embed_score=emb_score,
            w_emb=W_EMB,
        )
        scored.append((composite, r))

    scored.sort(key=lambda t: t[0], reverse=True)

    # ── Phase 3: Coherence pass (T4) ────────────────────────────────────
    # Jaccard deduplication — keep best-scoring of near-duplicate passages
    kept: List[Tuple[float, sqlite3.Row]] = []
    kept_token_sets: List[Set[str]] = []
    for score, r in scored:
        ts = _token_set(r[4][:400])
        duplicate = False
        for existing_ts in kept_token_sets:
            if _jaccard(ts, existing_ts) >= JACCARD_DUP_THRESH:
                duplicate = True
                break
        if not duplicate:
            kept.append((score, r))
            kept_token_sets.append(ts)

    top = kept[:limit * 2]  # take extra before final trim
    norm_scores = bm25.normalize([s for s, _ in top])

    results: List[SearchResult] = []
    for (_, r), norm in zip(top, norm_scores):
        cid, doc_id, page_num, section, content, tok_count, prev_id, next_id, title, fp, ftype = r
        snip = _make_snippet(content, pq.tokens + pq.stems)
        results.append(SearchResult(
            chunk_id=cid, doc_id=doc_id, title=title,
            file_path=fp, file_type=ftype,
            page_num=int(page_num), section=section,
            snippet=snip, score=round(float(norm), 4),
            intent_labels=pq.intents,
            structure_type=struct_map.get(cid, "exposition"),
            expansion_debug={
                "stems": pq.stems[:8],
                "direct": pq.direct_stems[:8],
                "concepts": pq.concept_stems[:8],
                "cooccurrence": cooc_terms[:8],
            },
        ))

    results = results[:limit]

    # Adjacency boosting: lightly promote results whose neighbor also scored well
    scored_ids = {r.chunk_id for r in results}
    for r in results:
        neighbor = conn.execute(
            "SELECT id FROM pages_chunks WHERE id=? OR id=?",
            (r.chunk_id, r.chunk_id),  # placeholder; checked via set
        )
        # Simpler: just tag results whose prev/next is also in results
        pr = conn.execute(
            "SELECT prev_id, next_id FROM pages_chunks WHERE id=?", (r.chunk_id,)
        ).fetchone()
        if pr and (pr[0] in scored_ids or pr[1] in scored_ids):
            r.score = min(1.0, r.score + 0.02)

    facet_doc_ids = list({r.doc_id for r in results})
    facets = facets_for_docs(conn, facet_doc_ids)

    # Build expansion debug for UI
    expansion_debug: Dict[str, list] = {}
    if results:
        expansion_debug = results[0].expansion_debug

    _record_history(conn, raw_query)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return SearchResponse(
        query=raw_query, results=results, facets=facets,
        elapsed_ms=round(elapsed, 2), intents=pq.intents,
        expansion_debug=expansion_debug,
    )


def history(conn: sqlite3.Connection, limit: int = 30) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT query FROM search_history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r[0] for r in rows]


def _record_history(conn: sqlite3.Connection, q: str) -> None:
    try:
        conn.execute(
            "INSERT INTO search_history(query,created_at) VALUES(?,?)",
            (q, time.time()),
        )
        conn.execute(
            """DELETE FROM search_history WHERE id NOT IN
               (SELECT id FROM search_history ORDER BY id DESC LIMIT 200)"""
        )
    except Exception:
        pass
