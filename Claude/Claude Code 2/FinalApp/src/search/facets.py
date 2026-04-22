"""Facet aggregation over a result set's document IDs."""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Set, Tuple


def facets_for_docs(
    conn: sqlite3.Connection,
    doc_ids: List[str],
) -> Dict[str, List[Tuple[str, int]]]:
    if not doc_ids:
        return {}
    ph = ",".join("?" * len(doc_ids))
    result: Dict[str, List[Tuple[str, int]]] = {}

    for col in ("author", "year", "file_type", "collection"):
        rows = conn.execute(
            f"""SELECT {col}, COUNT(*) as n FROM documents
                WHERE id IN ({ph}) AND {col} IS NOT NULL
                GROUP BY {col} ORDER BY n DESC""",
            doc_ids,
        ).fetchall()
        result[col] = [(str(r[0]), int(r[1])) for r in rows]

    # Tags
    tag_rows = conn.execute(
        f"""SELECT tag, COUNT(*) as n FROM doc_tags
            WHERE doc_id IN ({ph}) GROUP BY tag ORDER BY n DESC""",
        doc_ids,
    ).fetchall()
    result["tag"] = [(str(r[0]), int(r[1])) for r in tag_rows]

    return result
