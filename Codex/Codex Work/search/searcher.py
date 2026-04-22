from src.index.schema import get_db_connection
from src.search.query_parser import parse_query
from src.search.bm25 import calculate_bm25_scores

def _escape_fts_term(term: str) -> str:
    """
    Escape an arbitrary query term for FTS5.
    Using quoted terms avoids malformed MATCH clauses for punctuation-heavy input.
    """
    safe = term.replace('"', '""').strip()
    if not safe:
        return ""
    return f'"{safe}"*'

def execute_search(query_string: str, filters: dict = None, top_k: int = 50) -> list[dict]:
    """
    Executes a two-phase search:
    1. Fast candidate generation via SQLite FTS5 (combining exact phrases, terms, synonyms).
    2. BM25 reranking using pure Python implementation based on document stats.
    """
    parsed = parse_query(query_string)

    if not parsed["exact_phrases"] and not parsed["terms"]:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()

    # --- PHASE 1: Candidate Generation via FTS5 ---
    fts_queries = []

    # Exact phrases must match exactly
    for phrase in parsed["exact_phrases"]:
        fts_queries.append(f'"{phrase}"')

    # Terms (using simple OR for broad recall in candidate phase)
    all_terms = parsed["terms"] + parsed["stemmed_terms"] + parsed["expanded_terms"]
    # Remove duplicates while preserving order for deterministic query behavior
    all_terms = list(dict.fromkeys(all_terms))

    if all_terms:
        # FTS5 syntax for OR matching of terms
        safe_terms = [_escape_fts_term(term) for term in all_terms]
        safe_terms = [term for term in safe_terms if term]
        if safe_terms:
            term_query = " OR ".join(safe_terms)
            if fts_queries:
                 fts_queries.append(f"({term_query})")
            else:
                 fts_queries.append(term_query)

    fts_query_string = " AND ".join(fts_queries)

    # Base query
    sql = """
        SELECT c.docId, c.chunkId, c.content, d.title, d.pageCount, d.author, d.year, d.fileType
        FROM chunks_fts f
        JOIN pages_chunks c ON f.chunkId = c.chunkId
        JOIN documents d ON c.docId = d.id
        WHERE chunks_fts MATCH ?
    """
    params = [fts_query_string]

    # Apply pre-filters (facets)
    if filters:
        for key, value in filters.items():
            if value:
                # Ensure the column exists to prevent injection, basic check
                if key in ['author', 'year', 'fileType']:
                    sql += f" AND d.{key} = ?"
                    params.append(value)

    # Limit candidate generation to top 200 based on basic FTS rank to keep it fast
    sql += " ORDER BY rank LIMIT 200"

    try:
        cursor.execute(sql, params)
        candidates = cursor.fetchall()
    except Exception as e:
        # FTS error (e.g. malformed query string)
        conn.close()
        return []

    if not candidates:
        conn.close()
        return []

    candidate_doc_ids = list(set([row['docId'] for row in candidates]))

    # --- PHASE 2: BM25 Reranking ---
    # We rank based on the base terms and stemmed terms for scoring
    scoring_terms = parsed["stemmed_terms"] if parsed["stemmed_terms"] else parsed["terms"]
    bm25_scores = calculate_bm25_scores(scoring_terms, candidate_doc_ids)

    # Format and sort results
    results_map = {}
    for row in candidates:
        doc_id = row['docId']
        chunk_id = row['chunkId']

        # We might have multiple chunks per document matched in candidates.
        # We group by document, and keep the best chunk as snippet, or aggregate.
        # For simplicity, we create a result per document with the first matched snippet.
        if doc_id not in results_map:
            results_map[doc_id] = {
                "doc_id": doc_id,
                "title": row['title'],
                "author": row['author'],
                "year": row['year'],
                "fileType": row['fileType'],
                "snippet": row['content'][:300] + "...", # Basic snippet
                "score": bm25_scores.get(doc_id, 0.0)
            }

    conn.close()

    # Sort by BM25 score descending
    sorted_results = sorted(results_map.values(), key=lambda x: x['score'], reverse=True)
    return sorted_results[:top_k]
