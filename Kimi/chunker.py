"""
Semantic chunking per Sheet 14.
Layers: paragraphs -> sentences -> token cap (512) with boundary respect.
"""
import re
import hashlib
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_TOKENS = 512
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"'])')

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    doc_id: int
    page_num: int
    chunk_id: str
    content: str
    section_header: Optional[str]
    start_char: int
    end_char: int
    token_count: int
    prev_id: Optional[str]
    next_id: Optional[str]

# ---------------------------------------------------------------------------
# Splitters
# ---------------------------------------------------------------------------
def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in text.split('\n\n') if p.strip()]

def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]

def _token_count(text: str) -> int:
    return len(re.findall(r'\b[a-zA-Z]{2,}\b', text.lower()))

def _stable_id(file_path: str, page: int, start: int, end: int) -> str:
    return hashlib.sha1(f"{file_path}|{page}|{start}|{end}".encode()).hexdigest()[:12]

# ---------------------------------------------------------------------------
# Main chunker
# ---------------------------------------------------------------------------
def chunk_document(doc_id: int, file_path: str, pages: List[str]) -> List[Chunk]:
    """
    :param pages: list of raw text per page (1-based indexing expected by caller)
    :returns: list of Chunk objects with stable IDs and prev/next links.
    """
    all_chunks: List[Chunk] = []
    prev_id: Optional[str] = None
    doc_offset = 0

    for page_idx, page_text in enumerate(pages, start=1):
        if not page_text or not page_text.strip():
            doc_offset += 1
            continue

        paragraphs = split_paragraphs(page_text)
        page_local_offset = 0

        buffer_texts: List[str] = []
        buffer_tokens = 0
        buffer_start = 0

        def flush():
            nonlocal prev_id, buffer_texts, buffer_tokens, buffer_start
            if not buffer_texts:
                return
            content = " ".join(buffer_texts)
            abs_start = doc_offset + buffer_start
            cid = _stable_id(file_path, page_idx, abs_start, abs_start + len(content))
            chunk = Chunk(
                doc_id=doc_id,
                page_num=page_idx,
                chunk_id=cid,
                content=content,
                section_header=None,          # header heuristics can be added here
                start_char=abs_start,
                end_char=abs_start + len(content),
                token_count=buffer_tokens,
                prev_id=prev_id,
                next_id=None,
            )
            if prev_id and all_chunks:
                all_chunks[-1].next_id = cid
            all_chunks.append(chunk)
            prev_id = cid
            buffer_texts = []
            buffer_tokens = 0

        for para in paragraphs:
            sentences = split_sentences(para)
            for sent in sentences:
                sent_len = _token_count(sent)
                # Respect sentence boundary: flush before if we'd exceed cap
                if buffer_tokens and (buffer_tokens + sent_len > MAX_TOKENS):
                    flush()
                    buffer_start = page_local_offset

                if not buffer_texts:
                    buffer_start = page_local_offset

                buffer_texts.append(sent)
                buffer_tokens += sent_len
                page_local_offset += len(sent) + 1   # +1 for inter-sentence space

            # Paragraph break: flush if chunk is >70% of max to keep chunks balanced
            if buffer_tokens and buffer_tokens > int(MAX_TOKENS * 0.7):
                flush()

        if buffer_texts:
            flush()

        doc_offset += len(page_text) + 1

    return all_chunks
