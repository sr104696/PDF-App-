"""
File Hash Module - Unchanged from original.
"""
import hashlib


def generate_chunk_id(file_path: str, page_num: int, start_char: int) -> str:
    """
    Generate a stable chunk ID using SHA1.
    
    Args:
        file_path: Path to the file.
        page_num: Page number.
        start_char: Starting character position.
        
    Returns:
        SHA1 hash of the combined string.
    """
    unique_string = f"{file_path}_{page_num}_{start_char}"
    return hashlib.sha1(unique_string.encode('utf-8')).hexdigest()


def generate_doc_id(file_path: str) -> str:
    """
    Generate a stable doc ID using SHA1.
    
    Args:
        file_path: Path to the file.
        
    Returns:
        SHA1 hash of the file path.
    """
    return hashlib.sha1(file_path.encode('utf-8')).hexdigest()
