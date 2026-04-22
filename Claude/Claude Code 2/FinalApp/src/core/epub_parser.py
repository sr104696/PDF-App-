"""EPUB text extractor.

Uses ebooklib + BeautifulSoup. Each chapter becomes one 'page'.
Returns a list of PageText (same type as pdf_parser so the rest of
the pipeline is format-agnostic).
"""
from __future__ import annotations

import logging
from typing import List

from .pdf_parser import PageText

log = logging.getLogger(__name__)


def extract_pages(file_path: str) -> List[PageText]:
    """Extract chapters from an EPUB as PageText objects."""
    try:
        import ebooklib  # type: ignore
        from ebooklib import epub
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError as e:
        raise ImportError(f"ebooklib and beautifulsoup4 are required for EPUB: {e}")

    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        raise RuntimeError(f"Could not open EPUB {file_path}: {e}")

    pages: List[PageText] = []
    chapter_num = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        chapter_num += 1
        try:
            content = item.get_content()
            soup = BeautifulSoup(content, "html.parser")
            # Strip scripts and styles
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            if not text.strip():
                continue
            # Heading hint from first heading tag
            heading = None
            h = soup.find(["h1", "h2", "h3"])
            if h:
                heading = h.get_text(strip=True)[:80] or None
            pages.append(PageText(chapter_num, text, heading))
        except Exception as e:
            log.debug("EPUB chapter %d parse error: %s", chapter_num, e)
            continue

    return pages
