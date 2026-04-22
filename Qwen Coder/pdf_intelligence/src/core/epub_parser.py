"""
EPUB Parser Module - Optimized version with improved error handling.
"""
from typing import List, Dict

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    ebooklib = None
    BeautifulSoup = None


def extract_text_from_epub(file_path: str) -> List[Dict]:
    """
    Extracts text from an EPUB file.
    
    Args:
        file_path: Path to the EPUB file.
        
    Returns:
        A list of dicts: [{'page_num': 1, 'text': '...'}, ...]
        Here 'page_num' refers to document parts/chapters.
        
    Raises:
        ImportError: If ebooklib or BeautifulSoup is not installed.
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is not a valid EPUB or is corrupted.
    """
    if ebooklib is None or BeautifulSoup is None:
        raise ImportError("ebooklib or BeautifulSoup is not installed. Cannot parse EPUB.")
    
    import os
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    pages_data = []
    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read EPUB {file_path}: {e}")
    
    chapter_num = 1
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            try:
                soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
                if text:
                    pages_data.append({
                        "page_num": chapter_num,
                        "text": text
                    })
                    chapter_num += 1
            except Exception as e:
                # Log warning but continue with other chapters
                print(f"Warning: Failed to extract text from chapter {chapter_num}: {e}")
                chapter_num += 1
                continue
    
    return pages_data
