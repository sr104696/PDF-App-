"""
facets.py — SQL-driven facet aggregation (sheet 16).

Facets are derived from the *current result set* (not the whole corpus) so
counts reflect what the user actually sees. This avoids "dead end" filters
that would yield zero results.

Facet types implemented:
  author     — ValueFilter on documents.author
  year       — RangeFilter on documents.year
  fileType   — ValueFilter on documents.fileType
  collection — ValueFilter on documents.collection
  tag        — ValueFilter on doc_tags.tag

The sidebar uses these counts to grey out zero-hit options in real time.
"""
from __future__ import annotations

from src.index.schema import get_db_connection, DB_PATH


def facets_for_docs(
    doc_ids: list[str],
    db_path: str = DB_PATH,
) -> dict[str, list[dict]]:
    """
    Compute facet counts for a set of document IDs.

    Parameters
    ----------
    doc_ids : List of document ID strings from the current result set.

    Returns
    -------
    dict with keys: 'authors', 'years', 'fileTypes', 'collections', 'tags'.
    Each value is a list of {'name': str, 'count': int} dicts.
    """
    if not doc_ids:
        return {"authors": [], "years": [], "fileTypes": [], "collections": [], "tags": []}

    ph = ",".join("?" * len(doc_ids))
    conn = get_db_connection(db_path)
    try:
        def _agg(col: str) -> list[dict]:
            rows = conn.execute(
                f"""
                SELECT {col} AS name, COUNT(*) AS count
                FROM documents
                WHERE id IN ({ph})
                  AND {col} IS NOT NULL
                  AND {col} != ''
                GROUP BY {col}
                ORDER BY count DESC
                """,
                doc_ids,
            ).fetchall()
            return [{"name": r["name"], "count": r["count"]} for r in rows]

        authors = _agg("author")
        years = _agg("year")
        file_types = _agg("fileType")
        collections = _agg("collection")

        tags_rows = conn.execute(
            f"""
            SELECT tag AS name, COUNT(*) AS count
            FROM doc_tags
            WHERE docId IN ({ph})
            GROUP BY tag
            ORDER BY count DESC
            """,
            doc_ids,
        ).fetchall()
        tags = [{"name": r["name"], "count": r["count"]} for r in tags_rows]

        return {
            "authors": authors,
            "years": years,
            "fileTypes": file_types,
            "collections": collections,
            "tags": tags,
        }
    finally:
        conn.close()


def all_facets(db_path: str = DB_PATH) -> dict[str, list[dict]]:
    """Return facet counts across the entire library (for sidebar on load)."""
    conn = get_db_connection(db_path)
    try:
        all_ids = [r[0] for r in conn.execute("SELECT id FROM documents").fetchall()]
    finally:
        conn.close()
    return facets_for_docs(all_ids, db_path)
