"""Pure-Python Okapi BM25 with multi-signal composite scoring.

score_chunk() accepts multiple weighted term sets and returns a
composite BM25 score. No numpy required.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from ..utils.constants import BM25_K1, BM25_B


@dataclass
class CorpusStats:
    n_docs: int
    avg_dl: float

    @property
    def safe_avg_dl(self) -> float:
        return self.avg_dl if self.avg_dl > 0 else 1.0


def idf(n_docs: int, df: int) -> float:
    """Okapi BM25 IDF with +1 smoothing (always >= 0)."""
    if n_docs <= 0 or df <= 0:
        return 0.0
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def _bm25_terms(
    query_terms: Sequence[str],
    tf_in_chunk: Dict[str, int],
    chunk_len: int,
    df_lookup: Dict[str, int],
    stats: CorpusStats,
    k1: float,
    b: float,
) -> float:
    if not query_terms or chunk_len <= 0:
        return 0.0
    avgdl = stats.safe_avg_dl
    score = 0.0
    for term in query_terms:
        tf = tf_in_chunk.get(term, 0)
        if tf == 0:
            continue
        df = df_lookup.get(term, 0)
        if df <= 0:
            continue
        term_idf = idf(stats.n_docs, df)
        denom = tf + k1 * (1.0 - b + b * (chunk_len / avgdl))
        if denom > 0:
            score += term_idf * ((tf * (k1 + 1.0)) / denom)
    return score


def score_chunk(
    *,
    # Primary signals
    stem_terms: Sequence[str],
    direct_terms: Sequence[str],
    concept_terms: Sequence[str],
    cooc_terms: Sequence[str],
    # Per-chunk data
    tf_in_chunk: Dict[str, int],
    chunk_len: int,
    df_lookup: Dict[str, int],
    stats: CorpusStats,
    # Signal weights
    w_stem: float = 1.00,
    w_syn:  float = 0.85,
    w_con:  float = 0.60,
    w_cooc: float = 0.45,
    # Bonus signals (flat additions)
    struct_bonus: float = 0.0,
    prox_bonus: float = 0.0,
    header_bonus: float = 0.0,
    embed_score: float = 0.0,
    w_emb: float = 0.30,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    s_stem  = _bm25_terms(stem_terms,    tf_in_chunk, chunk_len, df_lookup, stats, k1, b)
    s_syn   = _bm25_terms(direct_terms,  tf_in_chunk, chunk_len, df_lookup, stats, k1, b)
    s_con   = _bm25_terms(concept_terms, tf_in_chunk, chunk_len, df_lookup, stats, k1, b)
    s_cooc  = _bm25_terms(cooc_terms,    tf_in_chunk, chunk_len, df_lookup, stats, k1, b)

    return (
        w_stem  * s_stem  +
        w_syn   * s_syn   +
        w_con   * s_con   +
        w_cooc  * s_cooc  +
        w_emb   * embed_score +
        struct_bonus +
        prox_bonus +
        header_bonus
    )


def normalize(scores: Iterable[float]) -> List[float]:
    """Min-max normalize to [0, 1]."""
    s = list(scores)
    if not s:
        return s
    lo, hi = min(s), max(s)
    if hi - lo < 1e-12:
        return [1.0 if hi > 0 else 0.0 for _ in s]
    return [(x - lo) / (hi - lo) for x in s]
