"""Facet aggregation (sheet 16).

Adapted from the faceted-search (PHP) ingest: instead of in-memory bitmaps,
we run small SQL aggregates restricted to the candidate result set. This
keeps memory flat regardless of corpus size.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Sequence


def facets_for_docs(
    conn: sqlite3.Connection,
    doc_ids: Sequence[int],
    fields: Sequence[str] = ("file_type", "author", "year", "collection"),
) -> Dict[str, List[tuple[str, int]]]:
    """Return {field: [(value, count), ...]} for the given document IDs."""
    if not doc_ids:
        return {f: [] for f in fields}
    placeholders = ",".join("?" * len(doc_ids))
    out: Dict[str, List[tuple[str, int]]] = {}
    for f in fields:
        if f not in {"file_type", "author", "year", "collection"}:
            continue
        rows = conn.execute(
            f"""SELECT {f}, COUNT(*) c FROM documents
                WHERE id IN ({placeholders}) AND {f} IS NOT NULL AND {f} <> ''
                GROUP BY {f} ORDER BY c DESC LIMIT 25""",
            tuple(doc_ids),
        ).fetchall()
        out[f] = [(str(v), int(c)) for v, c in rows]
    return out
