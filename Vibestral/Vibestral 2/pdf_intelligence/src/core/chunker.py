# src/core/chunker.py
# Changes: Added CHUNK_HARD_CAP emergency split from Claude; kept Lovable's
# overlap/merge logic; fixed all mojibake; cross-page prev/next wiring preserved.
"""Layered semantic chunker (sheet 14, v2).

Strategy:
  1. Per page (or EPUB chapter) -- page boundaries are hard splits.
  2. Split by paragraphs (blank-line heuristic).
  3. Split by sentences (NLTK punkt or regex fallback).
  4. Pack sentences into chunks <= MAX_CHUNK_TOKENS, never breaking a sentence.
  5. Emergency hard-split at CHUNK_HARD_CAP for pathological single sentences.
  6. Small overlap between consecutive chunks for context preservation.
  7. Stable SHA1 chunk IDs and prev/next links for context retrieval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .tokenizer import count_tokens, sentences
from ..utils.constants import (
    MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS, CHUNK_HARD_CAP,
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


def _hard_split(text: str, cap: int) -> List[str]:
    """Emergency word-boundary split when a sentence exceeds cap tokens."""
    words = text.split()
    chunks: List[str] = []
    current: List[str] = []
    count = 0
    for w in words:
        if count + 1 > cap and current:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(w)
        count += 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _pack_sentences(sents: List[str]) -> List[str]:
    """Greedy pack sentences into chunks under MAX_CHUNK_TOKENS, with overlap."""
    chunks: List[str] = []
    cur: List[str] = []
    cur_tokens = 0

    for sent in sents:
        n = max(1, count_tokens(sent))

        # Emergency hard-split for a single sentence exceeding CHUNK_HARD_CAP
        if n > CHUNK_HARD_CAP:
            if cur:
                chunks.append(" ".join(cur))
                cur, cur_tokens = [], 0
            chunks.extend(_hard_split(sent, MAX_CHUNK_TOKENS))
            continue

        if cur and cur_tokens + n > MAX_CHUNK_TOKENS:
            chunks.append(" ".join(cur))
            # Overlap: carry tail sentences worth ~CHUNK_OVERLAP_TOKENS
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

    # Merge tiny tail fragments into previous chunk to avoid noise
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

    # Wire prev/next links within page
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
    # Re-wire cross-page prev/next links
    for i, c in enumerate(out):
        c.prev_id = out[i - 1].id if i > 0 else None
        c.next_id = out[i + 1].id if i < len(out) - 1 else None
    return out
