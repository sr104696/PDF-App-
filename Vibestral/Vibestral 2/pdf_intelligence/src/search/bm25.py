# src/search/bm25.py
# Changes: Scores at CHUNK level (fixes document-level bug in Claude/Codex/Qwen/Vibestral);
# avg_dl is avg chunk token_count not avg document totalTokens; kept Lovable's pure-Python
# approach with no numpy; added min_max_normalize dict variant for Claude-style callers.
"""Pure-Python BM25 (Okapi). No numpy.

Scoring operates at the CHUNK level, not the document level. This is critical
for long documents: a 500-page book should not uniformly outscore a dense
10-page paper. Stats are precomputed at index time (indexer.py), so search
is just cheap SQL lookups + math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from ..utils.constants import BM25_K1, BM25_B


@dataclass
class CorpusStats:
    n_chunks: int    # total chunk count (NOT document count)
    avg_dl: float    # average chunk length in tokens

    @property
    def safe_avg_dl(self) -> float:
        return self.avg_dl if self.avg_dl > 0 else 1.0


def idf(n_chunks: int, df: int) -> float:
    """Okapi BM25 IDF with +1 smoothing (always >= 0)."""
    if n_chunks <= 0 or df <= 0:
        return 0.0
    return math.log(1.0 + (n_chunks - df + 0.5) / (df + 0.5))


def score_chunk(
    *,
    query_terms: Sequence[str],
    tf_in_chunk: Dict[str, int],
    chunk_len: int,
    df_lookup: Dict[str, int],
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
        term_idf = idf(stats.n_chunks, df)
        denom = tf + k1 * (1.0 - b + b * (chunk_len / avgdl))
        score += term_idf * ((tf * (k1 + 1.0)) / denom)
    return score


def normalize(scores: Iterable[float]) -> List[float]:
    """Min-max normalize to [0, 1]."""
    s = list(scores)
    if not s:
        return s
    lo, hi = min(s), max(s)
    if hi - lo < 1e-12:
        return [1.0 if hi > 0 else 0.0 for _ in s]
    return [(x - lo) / (hi - lo) for x in s]


def normalize_dict(scores: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalize a dict of scores to [0, 1]."""
    if not scores:
        return scores
    lo = min(scores.values())
    hi = max(scores.values())
    if hi - lo < 1e-12:
        return {k: 1.0 if hi > 0 else 0.0 for k in scores}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}
