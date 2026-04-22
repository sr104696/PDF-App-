"""Stable IDs and file fingerprints."""
import hashlib
import os
from pathlib import Path


def doc_fingerprint(path: str) -> tuple[int, float]:
    """Return (size_bytes, mtime) — cheap change-detection without hashing."""
    st = os.stat(path)
    return int(st.st_size), float(st.st_mtime)


def chunk_id(file_path: str, page_num: int, start_char: int, end_char: int) -> str:
    """Stable SHA1 ID for a chunk. Survives re-indexing unchanged files."""
    raw = f"{Path(file_path).resolve()}|{page_num}|{start_char}|{end_char}"
    return hashlib.sha1(raw.encode()).hexdigest()


def doc_id_from_path(file_path: str) -> str:
    """Stable SHA1 ID for a document path."""
    return hashlib.sha1(str(Path(file_path).resolve()).encode()).hexdigest()[:16]
