"""Pure-Python BM25 (Okapi). No numpy.

We compute BM25 against per-chunk term frequency (term_freq) and corpus-wide
document frequency (term_df). Stats are precomputed at index time (indexer.py),
so search is just a couple of cheap SQL lookups + math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from ..utils.constants import BM25_K1, BM25_B


@dataclass
class CorpusStats:
    n_docs: int            # total chunk count
    avg_dl: float          # average chunk length in tokens

    @property
    def safe_avg_dl(self) -> float:
        return self.avg_dl if self.avg_dl > 0 else 1.0


def idf(n_docs: int, df: int) -> float:
    """Okapi BM25 IDF with +1 smoothing (always >= 0)."""
    if n_docs <= 0 or df <= 0:
        return 0.0
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def score_chunk(
    *,
    query_terms: Sequence[str],         # stemmed
    tf_in_chunk: Dict[str, int],        # {stem: tf} for this chunk
    chunk_len: int,
    df_lookup: Dict[str, int],          # {stem: df}
    stats: CorpusStats,
    k1: float = BM25_K1,
    b: float = BM25_B,
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
        score += term_idf * ((tf * (k1 + 1.0)) / denom)
    return score


def normalize(scores: Iterable[float]) -> List[float]:
    """Min-max normalize to [0, 1] (sk-hybrid-search pattern)."""
    s = list(scores)
    if not s:
        return s
    lo, hi = min(s), max(s)
    if hi - lo < 1e-12:
        return [1.0 if hi > 0 else 0.0 for _ in s]
    return [(x - lo) / (hi - lo) for x in s]
