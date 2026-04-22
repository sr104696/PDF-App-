"""Stable IDs and file fingerprints. SHA1 is fine — not security-sensitive."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def chunk_id(file_path: str, page: int, start: int, end: int) -> str:
    """Stable chunk identifier (sheet 14): SHA1 over path + page + offsets."""
    h = hashlib.sha1()
    h.update(file_path.encode("utf-8", errors="replace"))
    h.update(f"|{page}|{start}|{end}".encode("ascii"))
    return h.hexdigest()


def doc_fingerprint(path: Path) -> tuple[int, float]:
    """Cheap fingerprint for incremental reindex (offline-search pattern):
    (size, mtime). Avoids hashing big PDFs on every scan."""
    st = os.stat(path)
    return st.st_size, st.st_mtime


def file_sha1(path: Path, chunk: int = 1 << 20) -> str:
    """Full content hash — only used when the user explicitly requests it."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()
