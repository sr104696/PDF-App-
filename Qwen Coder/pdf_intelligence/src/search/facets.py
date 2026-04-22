"""
Facets Module - Unchanged from original.
"""
from typing import Dict, List

from src.index.schema import get_db_connection


def get_facets() -> Dict[str, List[Dict]]:
    """
    Returns aggregated metadata counts for filtering (facets).
    
    Returns:
        Dictionary containing authors, years, and fileTypes with their counts.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    facets: Dict[str, List[Dict]] = {
        "authors": [],
        "years": [],
        "fileTypes": []
    }
    
    try:
        cursor.execute("""
            SELECT author, COUNT(*) as count 
            FROM documents 
            WHERE author IS NOT NULL AND author != '' 
            GROUP BY author 
            ORDER BY count DESC
        """)
        facets["authors"] = [{"name": row["author"], "count": row["count"]} for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT year, COUNT(*) as count 
            FROM documents 
            WHERE year IS NOT NULL AND year != '' 
            GROUP BY year 
            ORDER BY year DESC
        """)
        facets["years"] = [{"name": row["year"], "count": row["count"]} for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT fileType, COUNT(*) as count 
            FROM documents 
            WHERE fileType IS NOT NULL 
            GROUP BY fileType 
            ORDER BY count DESC
        """)
        facets["fileTypes"] = [{"name": row["fileType"], "count": row["count"]} for row in cursor.fetchall()]
    
    finally:
        conn.close()
    
    return facets
