"""
file_hash.py — Stable identifiers for documents and chunks.

Chunk IDs are derived from content-address (filePath + page + offsets), so
they survive re-indexing without change as long as the file hasn't changed.
Document IDs are a SHA1 of the normalised absolute path.
The (size, mtime) fingerprint lets the indexer skip unchanged files cheaply.
"""
import hashlib
import os


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def doc_id(file_path: str) -> str:
    """Stable document ID — SHA1 of the normalised absolute path."""
    return _sha1(os.path.normpath(os.path.abspath(file_path)))


def chunk_id(file_path: str, page_num: int, start_char: int, end_char: int) -> str:
    """
    Stable chunk ID — SHA1 of (normalised path | page | start | end).
    Changing any of these four values gives a new ID, so moved/edited
    files get fresh IDs while unchanged chunks keep theirs.
    """
    key = f"{os.path.normpath(os.path.abspath(file_path))}|{page_num}|{start_char}|{end_char}"
    return _sha1(key)


def doc_fingerprint(file_path: str) -> tuple[int, float]:
    """
    Return (file_size_bytes, mtime_float) for cheap change detection.
    The indexer stores this pair; on re-scan it skips files whose
    fingerprint matches the stored value.
    """
    stat = os.stat(file_path)
    return stat.st_size, stat.st_mtime
