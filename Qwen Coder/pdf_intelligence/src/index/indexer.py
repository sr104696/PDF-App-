"""
Indexer Module - Optimized version with batch operations and fixed SQL injection vulnerability.
"""
import os
from typing import Dict, List, Tuple

from src.index.schema import get_db_connection
from src.core.pdf_parser import extract_text_from_pdf
from src.core.epub_parser import extract_text_from_epub
from src.core.chunker import chunk_text
from src.utils.file_hash import generate_chunk_id, generate_doc_id
from src.core.tokenizer import tokenize


def index_file(file_path: str) -> None:
    """
    Indexes a single file (PDF or EPUB).
    
    Args:
        file_path: Path to the file to index.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file type is not supported.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_mtime = os.path.getmtime(file_path)
    file_size = os.path.getsize(file_path)
    file_ext = os.path.splitext(file_path)[1].lower()
    doc_id = generate_doc_id(file_path)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if file is already indexed and up-to-date
        cursor.execute("SELECT fileMtime FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if row and row['fileMtime'] == file_mtime:
            conn.close()
            return  # Already up to date
        
        # Remove old entries if re-indexing
        if row:
            cursor.execute("DELETE FROM pages_chunks WHERE docId = ?", (doc_id,))
            
            # Get all terms for this document to update DF
            cursor.execute("SELECT term FROM term_freq WHERE docId = ?", (doc_id,))
            old_terms = cursor.fetchall()
            for old_term_row in old_terms:
                term = old_term_row["term"]
                cursor.execute("UPDATE term_df SET doc_freq = doc_freq - 1 WHERE term = ?", (term,))
                cursor.execute("DELETE FROM term_df WHERE term = ? AND doc_freq <= 0", (term,))
            
            cursor.execute("DELETE FROM term_freq WHERE docId = ?", (doc_id,))
            cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        
        # Extract text
        if file_ext == '.pdf':
            pages_data = extract_text_from_pdf(file_path)
        elif file_ext == '.epub':
            pages_data = extract_text_from_epub(file_path)
        else:
            conn.close()
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        total_tokens = 0
        doc_term_freqs: Dict[str, int] = {}
        
        # Prepare batch inserts for chunks
        chunks_to_insert = []
        
        for page in pages_data:
            chunks = chunk_text(page['text'])
            for i, chunk in enumerate(chunks):
                chunk_id = generate_chunk_id(file_path, page['page_num'], chunk['start_char'])
                total_tokens += chunk['token_count']
                
                # Calculate term frequencies for this chunk
                tokens = tokenize(chunk['text'])
                for token in tokens:
                    doc_term_freqs[token] = doc_term_freqs.get(token, 0) + 1
                
                chunks_to_insert.append((
                    chunk_id, doc_id, page['page_num'], chunk_id,
                    chunk['text'], chunk['start_char'], chunk['end_char'],
                    chunk['token_count']
                ))
        
        # Batch insert chunks
        if chunks_to_insert:
            cursor.executemany("""
                INSERT INTO pages_chunks (id, docId, pageNum, chunkId, content, startChar, endChar, tokenCount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, chunks_to_insert)
        
        # Insert Document metadata
        title = os.path.basename(file_path)
        cursor.execute("""
            INSERT INTO documents (id, title, filePath, pageCount, fileSize, fileType, fileMtime, totalTokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, title, file_path, len(pages_data), file_size, file_ext, file_mtime, total_tokens))
        
        # Batch insert term frequencies
        if doc_term_freqs:
            term_freq_data = [(doc_id, term, freq) for term, freq in doc_term_freqs.items()]
            cursor.executemany("""
                INSERT INTO term_freq (docId, term, freq) VALUES (?, ?, ?)
            """, term_freq_data)
            
            # Update Document Frequencies
            # First, get existing terms
            existing_terms = set()
            cursor.execute("SELECT term FROM term_df")
            for row in cursor.fetchall():
                existing_terms.add(row['term'])
            
            # Prepare updates and inserts
            terms_to_update = []
            terms_to_insert = []
            
            for term in doc_term_freqs.keys():
                if term in existing_terms:
                    terms_to_update.append((term,))
                else:
                    terms_to_insert.append((term, 1))
            
            # Batch update existing terms
            if terms_to_update:
                cursor.executemany("""
                    UPDATE term_df SET doc_freq = doc_freq + 1 WHERE term = ?
                """, terms_to_update)
            
            # Batch insert new terms
            if terms_to_insert:
                cursor.executemany("""
                    INSERT INTO term_df (term, doc_freq) VALUES (?, 1)
                """, terms_to_insert)
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()
