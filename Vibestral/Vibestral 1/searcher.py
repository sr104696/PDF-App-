"""
Searcher Module - Optimized version with fixed FTS5 join and improved snippet generation.
"""
from typing import List, Dict, Optional

from schema import get_db_connection
from query_parser import parse_query
from bm25 import calculate_bm25_scores


def execute_search(query_string: str, filters: Optional[Dict] = None, top_k: int = 50) -> List[Dict]:
    """
    Executes a two-phase search:
    1. Fast candidate generation via SQLite FTS5 (combining exact phrases, terms, synonyms).
    2. BM25 reranking using pure Python implementation based on document stats.
    
    Args:
        query_string: The search query.
        filters: Optional dictionary of filters (author, year, fileType).
        top_k: Maximum number of results to return.
        
    Returns:
        List of search results sorted by relevance score.
    """
    parsed = parse_query(query_string)
    
    if not parsed["exact_phrases"] and not parsed["terms"]:
        return []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # --- PHASE 1: Candidate Generation via FTS5 ---
        fts_queries = []
        
        # Exact phrases must match exactly
        for phrase in parsed["exact_phrases"]:
            fts_queries.append(f'"{phrase}"')
        
        # Terms (using simple OR for broad recall in candidate phase)
        all_terms = parsed["terms"] + parsed["stemmed_terms"] + parsed["expanded_terms"]
        # Remove duplicates
        all_terms = list(set(all_terms))
        
        if all_terms:
            # FTS5 syntax for OR matching of terms
            term_query = " OR ".join([f"{term}*" for term in all_terms])
            if fts_queries:
                fts_queries.append(f"({term_query})")
            else:
                fts_queries.append(term_query)
        
        fts_query_string = " AND ".join(fts_queries)
        
        # Base query - FIXED: Use rowid for joining FTS table
        sql = """
            SELECT c.docId, c.chunkId, c.content, c.startChar, c.endChar, 
                   d.title, d.pageCount, d.author, d.year, d.fileType
            FROM chunks_fts f
            JOIN pages_chunks c ON f.rowid = c.rowid
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
        
        cursor.execute(sql, params)
        candidates = cursor.fetchall()
    except Exception as e:
        # FTS error (e.g. malformed query string)
        conn.close()
        print(f"Search error: {e}")
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
            # Generate better snippet with context
            snippet = generate_snippet(row['content'], row['startChar'], row['endChar'], scoring_terms)
            
            results_map[doc_id] = {
                "doc_id": doc_id,
                "title": row['title'],
                "author": row['author'],
                "year": row['year'],
                "fileType": row['fileType'],
                "snippet": snippet,
                "score": bm25_scores.get(doc_id, 0.0)
            }
    
    conn.close()
    
    # Sort by BM25 score descending
    sorted_results = sorted(results_map.values(), key=lambda x: x['score'], reverse=True)
    return sorted_results[:top_k]


def generate_snippet(content: str, start_char: int, end_char: int, 
                     terms: List[str], context_size: int = 150) -> str:
    """
    Generates a relevant snippet from content with context around matched terms.
    
    Args:
        content: The full chunk content.
        start_char: Start character position.
        end_char: End character position.
        terms: Search terms to highlight.
        context_size: Number of characters to show before/after the match.
        
    Returns:
        A formatted snippet string.
    """
    if not content:
        return ""
    
    # Find the first occurrence of any search term
    best_pos = -1
    best_term_len = 0
    
    content_lower = content.lower()
    for term in terms:
        pos = content_lower.find(term.lower())
        if pos != -1:
            if best_pos == -1 or pos < best_pos:
                best_pos = pos
                best_term_len = len(term)
    
    # If no term found, use the beginning of the content
    if best_pos == -1:
        start = max(0, 0)
        end = min(len(content), context_size * 2)
    else:
        # Center the snippet around the match
        start = max(0, best_pos - context_size)
        end = min(len(content), best_pos + best_term_len + context_size)
    
    snippet = content[start:end].strip()
    
    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    return snippet
