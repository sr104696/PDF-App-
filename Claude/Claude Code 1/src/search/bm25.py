"""
bm25.py — Pure-Python Okapi BM25 reranker (no numpy / no torch).

Implements the Okapi BM25 formula from Trotman et al. (2014) and the
dorianbrown/rank_bm25 reference implementation, adapted to work from
pre-stored term_freq / term_df SQLite tables instead of an in-memory corpus.

This is the Tier 2 ("Proper ranking") component described in sheet 15 and
sheet 21. It is called AFTER FTS5 candidate generation.

Scoring operates at the *chunk* level, not the document level, which is
more accurate for long documents (a 500-page book should not uniformly
score higher than a dense 10-page paper).

Parameters (tunable in constants.py):
  k1 = 1.5   — term-saturation; higher → TF growth curve is steeper
  b  = 0.75  — length normalisation; 1.0 = full normalisation, 0 = none
"""
from __future__ import annotations

import math
from typing import Sequence

from src.index.schema import get_db_connection, DB_PATH
from src.utils.constants import BM25_K1, BM25_B, BM25_EPSILON, SYNONYM_BOOST


def _idf(n: int, df: int) -> float:
    """
    IDF with the smoothed Okapi formula (avoids negative values):
      ln( (N - df + 0.5) / (df + 0.5) + 1 )
    """
    return math.log((n - df + 0.5) / (df + 0.5) + 1.0)


def _tf_weight(tf: int, doc_len: int, avg_dl: float) -> float:
    """Okapi BM25 TF weight with length normalisation."""
    if avg_dl == 0:
        avg_dl = 1.0
    return (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / avg_dl))


def min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    """
    Min-max normalise a dict of scores to [0, 1].
    Sheet 15: "critical and often skipped."
    Returns unchanged dict if all scores are identical.
    """
    if not scores:
        return scores
    lo = min(scores.values())
    hi = max(scores.values())
    if hi == lo:
        return {k: 1.0 for k in scores}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}


def score_chunks(
    query_terms: Sequence[str],
    candidate_chunk_ids: Sequence[str],
    synonym_terms: Sequence[str] | None = None,
    db_path: str = DB_PATH,
) -> dict[str, float]:
    """
    Compute BM25 scores for *candidate_chunk_ids* given *query_terms*.

    Parameters
    ----------
    query_terms         : Stemmed query tokens (primary signal).
    candidate_chunk_ids : Chunk IDs returned by FTS5 (up to CANDIDATE_LIMIT).
    synonym_terms       : Synonym expansions — score a small additive boost.
    db_path             : Database path.

    Returns
    -------
    dict mapping chunk_id → raw BM25 score (not yet normalised).
    """
    if not query_terms or not candidate_chunk_ids:
        return {}

    conn = get_db_connection(db_path)
    try:
        # ── Corpus statistics ────────────────────────────────────────────
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        avg_dl_row = conn.execute("SELECT AVG(totalTokens) FROM documents").fetchone()
        avg_dl: float = avg_dl_row[0] or 1.0

        # ── Per-chunk length ─────────────────────────────────────────────
        ph = ",".join("?" * len(candidate_chunk_ids))
        chunk_lens: dict[str, int] = {}
        for row in conn.execute(
            f"SELECT id, tokenCount FROM pages_chunks WHERE id IN ({ph})",
            list(candidate_chunk_ids),
        ):
            chunk_lens[row["id"]] = row["tokenCount"] or 1

        # ── Score accumulator ────────────────────────────────────────────
        scores: dict[str, float] = {cid: 0.0 for cid in candidate_chunk_ids}

        all_terms = list(query_terms)
        is_synonym = set()
        if synonym_terms:
            for s in synonym_terms:
                if s not in all_terms:
                    all_terms.append(s)
                    is_synonym.add(s)

        # Batch-fetch df for all query terms
        term_ph = ",".join("?" * len(all_terms))
        df_map: dict[str, int] = {}
        for row in conn.execute(
            f"SELECT term, df FROM term_df WHERE term IN ({term_ph})",
            all_terms,
        ):
            df_map[row["term"]] = row["df"]

        # For each term, batch-fetch TF across all candidate chunks
        for term in all_terms:
            df = df_map.get(term, 0)
            if df == 0:
                continue  # term not in corpus at all
            term_idf = _idf(n_docs, df)

            for row in conn.execute(
                f"""
                SELECT chunkId, tf
                FROM term_freq
                WHERE term = ? AND chunkId IN ({ph})
                """,
                [term] + list(candidate_chunk_ids),
            ):
                cid = row["chunkId"]
                tf = row["tf"] or 0
                if tf == 0:
                    continue
                dl = chunk_lens.get(cid, avg_dl)
                contrib = term_idf * _tf_weight(tf, dl, avg_dl)
                if term in is_synonym:
                    contrib *= SYNONYM_BOOST
                scores[cid] = scores.get(cid, 0.0) + contrib

        return scores

    finally:
        conn.close()
