"""
chunker.py — Layered semantic chunker (v2 sheet 14).

Replaces the original char-slicing splitIntoPages() with a four-layer
structure-aware splitter:

  Layer 1  Native page text is already split upstream (by pdf_parser / epub_parser).
  Layer 2  Split each page by blank lines → paragraph units.
  Layer 3  Oversized paragraphs split by sentence boundaries (NLTK punkt
           with regex fallback).
  Layer 4  Greedy-pack sentences up to MAX_CHUNK_TOKENS; carry a
           CHUNK_OVERLAP_TOKENS tail into the next chunk for context.

Additional invariants (from python-semantic-splitter pattern):
  - Tiny tail fragments (< MIN_CHUNK_TOKENS) merged into the previous chunk.
  - Hard cap at CHUNK_HARD_CAP tokens; emergency split at that boundary.
  - Stable SHA1 chunk IDs from (file_path, page_num, start_char, end_char).
  - Each chunk carries prev_id / next_id for context retrieval.
  - sectionHeader copied from PageText.heading_hint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.tokenizer import tokenize_words, count_words, tokenize_sentences
from src.utils.constants import (
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    CHUNK_HARD_CAP,
)
from src.utils import file_hash

if TYPE_CHECKING:
    from src.core.pdf_parser import PageText


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page_num: int
    content: str
    section_header: str
    start_char: int
    end_char: int
    token_count: int
    prev_id: str = ""
    next_id: str = ""


# ── Internal helpers ──────────────────────────────────────────────────────────
_BLANK_LINE_RE = re.compile(r"\n\s*\n")


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _BLANK_LINE_RE.split(text) if p.strip()]


def _hard_split(text: str, cap: int) -> list[str]:
    """Emergency word-boundary split when a sentence exceeds *cap* tokens."""
    words = text.split()
    chunks, current = [], []
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


def _pack_sentences(sentences: list[str], overlap_tail: str = "") -> list[str]:
    """
    Greedy-pack sentences into chunks ≤ MAX_CHUNK_TOKENS.
    Returns a list of chunk text strings.
    """
    result: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    if overlap_tail:
        current_parts.append(overlap_tail)
        current_tokens = count_words(overlap_tail)

    for sent in sentences:
        sent_tokens = count_words(sent)

        # Emergency hard-split if a single sentence exceeds CHUNK_HARD_CAP
        if sent_tokens > CHUNK_HARD_CAP:
            if current_parts:
                result.append(" ".join(current_parts))
                current_parts, current_tokens = [], 0
            for sub in _hard_split(sent, MAX_CHUNK_TOKENS):
                result.append(sub)
            continue

        if current_tokens + sent_tokens > MAX_CHUNK_TOKENS and current_parts:
            result.append(" ".join(current_parts))
            # Carry overlap: last few words of previous chunk
            tail_words = " ".join(current_parts).split()[-CHUNK_OVERLAP_TOKENS:]
            current_parts = [" ".join(tail_words)]
            current_tokens = len(tail_words)

        current_parts.append(sent)
        current_tokens += sent_tokens

    if current_parts:
        text = " ".join(current_parts)
        if text.strip():
            result.append(text)

    return result


# ── Public API ────────────────────────────────────────────────────────────────
def chunk_page(
    page: "PageText",
    file_path: str,
    doc_id: str,
) -> list[Chunk]:
    """
    Chunk a single page into Chunk objects.

    Parameters
    ----------
    page      : PageText from pdf_parser or epub_parser.
    file_path : Absolute path to the source file (for stable chunk IDs).
    doc_id    : SHA1 document ID (for the docId FK).
    """
    if not page.text.strip():
        return []

    section_header = page.heading_hint or ""
    paragraphs = _split_paragraphs(page.text)
    if not paragraphs:
        paragraphs = [page.text.strip()]

    # Collect all sentences in order
    all_sentences: list[str] = []
    for para in paragraphs:
        if count_words(para) <= MAX_CHUNK_TOKENS:
            all_sentences.extend(tokenize_sentences(para))
        else:
            # paragraph itself too big → sentence-split it
            all_sentences.extend(tokenize_sentences(para))

    chunk_texts = _pack_sentences(all_sentences)

    # Build Chunk objects with stable IDs and char offsets
    chunks: list[Chunk] = []
    char_cursor = 0

    for text in chunk_texts:
        token_count = count_words(text)
        if token_count < MIN_CHUNK_TOKENS and chunks:
            # Merge tiny tail into previous chunk
            prev = chunks[-1]
            merged_text = prev.content + " " + text
            merged_tokens = count_words(merged_text)
            new_end = char_cursor + len(text)
            cid = file_hash.chunk_id(file_path, page.page_num, prev.start_char, new_end)
            chunks[-1] = Chunk(
                chunk_id=cid,
                doc_id=doc_id,
                page_num=page.page_num,
                content=merged_text,
                section_header=section_header,
                start_char=prev.start_char,
                end_char=new_end,
                token_count=merged_tokens,
                prev_id=prev.prev_id,
            )
            char_cursor += len(text) + 1
            continue

        start = char_cursor
        end = char_cursor + len(text)
        cid = file_hash.chunk_id(file_path, page.page_num, start, end)

        chunks.append(Chunk(
            chunk_id=cid,
            doc_id=doc_id,
            page_num=page.page_num,
            content=text,
            section_header=section_header,
            start_char=start,
            end_char=end,
            token_count=token_count,
        ))
        char_cursor = end + 1

    # Wire prev_id / next_id linked list
    for i, chunk in enumerate(chunks):
        if i > 0:
            chunk.prev_id = chunks[i - 1].chunk_id
        if i < len(chunks) - 1:
            chunk.next_id = chunks[i + 1].chunk_id

    return chunks


def chunk_document(
    pages: list,
    file_path: str,
    doc_id: str,
) -> list[Chunk]:
    """
    Chunk all pages of a document.
    Wires prev_id/next_id across page boundaries as well.
    """
    all_chunks: list[Chunk] = []
    for page in pages:
        all_chunks.extend(chunk_page(page, file_path, doc_id))

    # Re-wire cross-page links (page-level wiring was done inside chunk_page)
    for i, chunk in enumerate(all_chunks):
        if i > 0 and not chunk.prev_id:
            chunk.prev_id = all_chunks[i - 1].chunk_id
        if i < len(all_chunks) - 1 and not chunk.next_id:
            chunk.next_id = all_chunks[i + 1].chunk_id

    return all_chunks
