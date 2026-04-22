"""
PDF Parser Module - Optimized version with improved error handling.
"""
import os
from typing import List, Dict, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def extract_text_from_pdf(file_path: str) -> List[Dict]:
    """
    Extracts text from a PDF file.
    
    Args:
        file_path: Path to the PDF file.
        
    Returns:
        A list of dicts: [{'page_num': 1, 'text': '...'}, ...]
        
    Raises:
        ImportError: If pdfplumber is not installed.
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is not a valid PDF or is corrupted.
    """
    if pdfplumber is None:
        raise ImportError("pdfplumber is not installed. Cannot parse PDF.")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    pages_data = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text:
                        pages_data.append({
                            "page_num": i + 1,
                            "text": text
                        })
                except Exception as e:
                    # Log warning but continue with other pages
                    print(f"Warning: Failed to extract text from page {i+1}: {e}")
                    continue
    except Exception as e:
        raise ValueError(f"Failed to parse PDF {file_path}: {e}")
    
    return pages_data
