"""Layered semantic chunker (sheet 14, v2).

Strategy:
  1. Per page (or per EPUB chapter) — keep page boundaries as hard splits.
  2. Split by paragraphs (blank-line heuristic).
  3. Split by sentences (NLTK punkt or regex fallback).
  4. Pack sentences into chunks <= MAX_CHUNK_TOKENS, never breaking a sentence.
  5. Apply a small overlap between consecutive chunks for context preservation
     (treesitter-chunker / python-semantic-splitter pattern, adapted to plain text).
  6. Emit stable chunk IDs (utils.file_hash.chunk_id) and prev/next links so
     the searcher can show context windows without re-reading the PDF.

Output: a list of `Chunk` objects. Caller persists them in SQLite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .tokenizer import count_tokens, sentences
from ..utils.constants import (
    MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS,
)
from ..utils.file_hash import chunk_id

_PARA_RE = re.compile(r"\n\s*\n+")


@dataclass
class Chunk:
    id: str
    page_num: int
    section: Optional[str]
    text: str
    token_count: int
    start_char: int
    end_char: int
    prev_id: Optional[str] = None
    next_id: Optional[str] = None


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in _PARA_RE.split(text) if p.strip()]


def _pack_sentences(sents: List[str]) -> List[str]:
    """Greedy pack sentences into chunks under MAX_CHUNK_TOKENS, with overlap."""
    chunks: List[str] = []
    cur: List[str] = []
    cur_tokens = 0
    for sent in sents:
        n = max(1, count_tokens(sent))
        if cur and cur_tokens + n > MAX_CHUNK_TOKENS:
            chunks.append(" ".join(cur))
            # overlap: carry tail sentences worth ~CHUNK_OVERLAP_TOKENS
            if CHUNK_OVERLAP_TOKENS > 0:
                tail: List[str] = []
                tail_tokens = 0
                for s in reversed(cur):
                    sn = max(1, count_tokens(s))
                    if tail_tokens + sn > CHUNK_OVERLAP_TOKENS:
                        break
                    tail.insert(0, s)
                    tail_tokens += sn
                cur = list(tail)
                cur_tokens = tail_tokens
            else:
                cur, cur_tokens = [], 0
        cur.append(sent)
        cur_tokens += n
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def chunk_page(
    *,
    file_path: str,
    page_num: int,
    text: str,
    section: Optional[str] = None,
) -> List[Chunk]:
    """Convert one page's text into a list of Chunk records."""
    text = (text or "").strip()
    if not text:
        return []

    pieces: List[str] = []
    for para in _paragraphs(text):
        if count_tokens(para) <= MAX_CHUNK_TOKENS:
            pieces.append(para)
        else:
            pieces.extend(_pack_sentences(sentences(para)))

    # Drop tiny tail fragments by merging into previous (avoid noise).
    cleaned: List[str] = []
    for p in pieces:
        if cleaned and count_tokens(p) < MIN_CHUNK_TOKENS:
            merged = cleaned[-1] + " " + p
            if count_tokens(merged) <= MAX_CHUNK_TOKENS + MIN_CHUNK_TOKENS:
                cleaned[-1] = merged
                continue
        cleaned.append(p)

    chunks: List[Chunk] = []
    cursor = 0
    for piece in cleaned:
        # Locate this piece in the original page text for char offsets.
        idx = text.find(piece[:60], cursor) if piece else -1
        if idx < 0:
            idx = cursor
        start = idx
        end = idx + len(piece)
        cursor = end
        cid = chunk_id(file_path, page_num, start, end)
        chunks.append(Chunk(
            id=cid,
            page_num=page_num,
            section=section,
            text=piece,
            token_count=count_tokens(piece),
            start_char=start,
            end_char=end,
        ))

    # Wire prev/next links.
    for i, c in enumerate(chunks):
        if i > 0:
            c.prev_id = chunks[i - 1].id
        if i < len(chunks) - 1:
            c.next_id = chunks[i + 1].id
    return chunks


def chunk_document(
    *,
    file_path: str,
    pages: Iterable[tuple[int, str, Optional[str]]],
) -> List[Chunk]:
    """Chunk a whole document. `pages` yields (page_num, text, section)."""
    out: List[Chunk] = []
    for page_num, text, section in pages:
        out.extend(chunk_page(
            file_path=file_path,
            page_num=page_num,
            text=text,
            section=section,
        ))
    # Wire cross-page prev/next as well.
    for i, c in enumerate(out):
        c.prev_id = out[i - 1].id if i > 0 else None
        c.next_id = out[i + 1].id if i < len(out) - 1 else None
    return out
