"""Layered semantic chunker with structure-type classification.

Strategy (per page / chapter):
  L1 — Split by blank lines (paragraphs).
  L2 — Split oversized paragraphs by sentences (NLTK / regex fallback).
  L3 — Greedy-pack sentences into chunks <= MAX_CHUNK_TOKENS.
  L4 — 32-token overlap between consecutive chunks.
  L5 — Merge tiny tail fragments (< MIN_CHUNK_TOKENS) into previous chunk.

Each Chunk gets:
  - Stable SHA1 ID (survives re-indexing)
  - prev_id / next_id for context retrieval
  - structure_type: dialogue | poetry | quote_block | list | heading_body | exposition
  - density_score: ratio of structural markers to tokens
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from .tokenizer import count_tokens, sentences
from ..utils.constants import (
    MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS,
)
from ..utils.file_hash import chunk_id as _make_id

_PARA_RE = re.compile(r"\n\s*\n+")

# ── Structure-type detection ────────────────────────────────────────────────
_DIALOGUE_MARKERS = re.compile(r'["\u201C\u201D\u2018\u2019]')
_EMDASH_RE = re.compile(r'[\u2014\u2013]|--')
_POETRY_RE = re.compile(r'(\n[ \t]*[A-Z][^\n]{0,60}\n){2,}')  # short lines, title-case
_LIST_RE = re.compile(r'^\s*[\-\*\u2022\d]+[\.\)]\s', re.MULTILINE)
_QUOTE_INTRO = re.compile(
    r'\b(said|wrote|noted|remarked|observed|declared|argued|stated|exclaimed|replied|whispered)\b',
    re.IGNORECASE
)
_ATTRIBUTION = re.compile(r'[\u201C\u201D"]{1}[^"]{10,300}[\u201C\u201D"]{1}')


def _classify_structure(text: str) -> Tuple[str, float]:
    """Return (structure_type, density_score 0-1)."""
    words = max(1, count_tokens(text))

    # Count markers
    dialogue_hits = len(_DIALOGUE_MARKERS.findall(text))
    em_hits = len(_EMDASH_RE.findall(text))
    list_hits = len(_LIST_RE.findall(text))
    attr_hits = len(_ATTRIBUTION.findall(text))
    quote_intro_hits = len(_QUOTE_INTRO.findall(text))

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    short_lines = sum(1 for l in lines if len(l.split()) <= 8) if lines else 0
    short_ratio = short_lines / max(1, len(lines))

    if list_hits >= 2:
        density = min(1.0, list_hits / (words / 10))
        return "list", density

    if attr_hits >= 1 or quote_intro_hits >= 1:
        density = min(1.0, (attr_hits + quote_intro_hits) / (words / 20))
        return "quote_block", density

    if short_ratio > 0.6 and len(lines) >= 4:
        density = short_ratio
        return "poetry", density

    if (dialogue_hits / max(1, words)) > 0.04 or em_hits >= 2:
        density = min(1.0, (dialogue_hits + em_hits * 2) / (words / 5))
        return "dialogue", density

    # heading_body: first line is short + title-case
    if lines and len(lines[0].split()) <= 8 and lines[0][0:1].isupper():
        return "heading_body", 0.4

    return "exposition", 0.1


# ── Chunk dataclass ─────────────────────────────────────────────────────────
@dataclass
class Chunk:
    id: str
    page_num: int
    section: Optional[str]
    text: str
    token_count: int
    start_char: int
    end_char: int
    structure_type: str = "exposition"
    density_score: float = 0.1
    prev_id: Optional[str] = None
    next_id: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────
def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in _PARA_RE.split(text) if p.strip()]


def _pack_sentences(sents: List[str]) -> List[str]:
    """Greedy-pack sentences with overlap."""
    chunks: List[str] = []
    cur: List[str] = []
    cur_tokens = 0
    for sent in sents:
        n = max(1, count_tokens(sent))
        if cur and cur_tokens + n > MAX_CHUNK_TOKENS:
            chunks.append(" ".join(cur))
            # carry overlap tail
            if CHUNK_OVERLAP_TOKENS > 0:
                tail: List[str] = []
                tail_t = 0
                for s in reversed(cur):
                    sn = max(1, count_tokens(s))
                    if tail_t + sn > CHUNK_OVERLAP_TOKENS:
                        break
                    tail.insert(0, s)
                    tail_t += sn
                cur, cur_tokens = list(tail), tail_t
            else:
                cur, cur_tokens = [], 0
        cur.append(sent)
        cur_tokens += n
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# ── Public API ───────────────────────────────────────────────────────────────
def chunk_page(
    *,
    file_path: str,
    page_num: int,
    text: str,
    section: Optional[str] = None,
) -> List[Chunk]:
    text = (text or "").strip()
    if not text:
        return []

    pieces: List[str] = []
    for para in _paragraphs(text):
        if count_tokens(para) <= MAX_CHUNK_TOKENS:
            pieces.append(para)
        else:
            pieces.extend(_pack_sentences(sentences(para)))

    # Merge tiny tail fragments
    cleaned: List[str] = []
    for p in pieces:
        if cleaned and count_tokens(p) < MIN_CHUNK_TOKENS:
            merged = cleaned[-1] + " " + p
            if count_tokens(merged) <= MAX_CHUNK_TOKENS + MIN_CHUNK_TOKENS:
                cleaned[-1] = merged
                continue
        if count_tokens(p) >= MIN_CHUNK_TOKENS:
            cleaned.append(p)

    chunks: List[Chunk] = []
    cursor = 0
    for piece in cleaned:
        # Locate piece in original text for stable char offsets
        probe = piece[:60] if len(piece) >= 60 else piece
        idx = text.find(probe, cursor)
        if idx < 0:
            idx = cursor
        start = idx
        end = idx + len(piece)
        cursor = end
        cid = _make_id(file_path, page_num, start, end)
        struct, density = _classify_structure(piece)
        chunks.append(Chunk(
            id=cid, page_num=page_num, section=section,
            text=piece, token_count=count_tokens(piece),
            start_char=start, end_char=end,
            structure_type=struct, density_score=density,
        ))

    # Wire prev/next
    for i, c in enumerate(chunks):
        c.prev_id = chunks[i - 1].id if i > 0 else None
        c.next_id = chunks[i + 1].id if i < len(chunks) - 1 else None
    return chunks


def chunk_document(
    *,
    file_path: str,
    pages: Iterable[tuple],  # (page_num, text, section)
) -> List[Chunk]:
    out: List[Chunk] = []
    for page_num, text, section in pages:
        out.extend(chunk_page(
            file_path=file_path, page_num=page_num,
            text=text, section=section,
        ))
    # Re-wire across page boundaries
    for i, c in enumerate(out):
        c.prev_id = out[i - 1].id if i > 0 else None
        c.next_id = out[i + 1].id if i < len(out) - 1 else None
    return out
