# src/utils/file_hash.py
# Changes: Added doc_id() (SHA1 of normalised path) for stable document IDs;
# kept chunk_id() and doc_fingerprint() from Lovable; normalised path handling.
"""Stable IDs and file fingerprints. SHA1 is fine -- not security-sensitive."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def doc_id(file_path: str | Path) -> str:
    """Stable document ID -- SHA1 of the normalised absolute path."""
    return _sha1(os.path.normpath(os.path.abspath(str(file_path))))


def chunk_id(file_path: str | Path, page: int, start: int, end: int) -> str:
    """Stable chunk identifier: SHA1 over normalised path + page + offsets."""
    key = f"{os.path.normpath(os.path.abspath(str(file_path)))}|{page}|{start}|{end}"
    return _sha1(key)


def doc_fingerprint(path: str | Path) -> tuple[int, float]:
    """Cheap fingerprint for incremental reindex: (size_bytes, mtime_float).
    Avoids hashing large PDFs on every scan."""
    st = os.stat(str(path))
    return st.st_size, st.st_mtime


def file_sha1(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """Full content hash -- only used when explicitly requested."""
    h = hashlib.sha1()
    with open(str(path), "rb") as f:
        for buf in iter(lambda: f.read(chunk_size), b""):
            h.update(buf)
    return h.hexdigest()
