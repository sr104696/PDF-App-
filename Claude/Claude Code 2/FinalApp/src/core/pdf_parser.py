"""PDF text extractor.

Tries pdfplumber first (accurate layout + heading hints),
falls back to pypdf (pure Python, strict=False).
Returns a list of PageText named-tuples.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

log = logging.getLogger(__name__)

_HEADING_RE = re.compile(
    r"^(?:[A-Z][A-Z\s]{2,}[A-Z]|(?:[A-Z][a-z]+\s+){1,5}[A-Z][a-z]+)$"
)


@dataclass
class PageText:
    page_num: int
    text: str
    heading_hint: Optional[str]  # first short title-case / all-caps line on page


def _heading_from(text: str) -> Optional[str]:
    for line in text.splitlines():
        line = line.strip()
        if 3 < len(line) < 80 and _HEADING_RE.match(line):
            return line
    return None


def extract_pages(file_path: str, ocr: bool = False) -> List[PageText]:
    """Extract text page-by-page. Raises on total failure."""
    pages = _try_pdfplumber(file_path)
    if pages is None:
        pages = _try_pypdf(file_path)
    if pages is None:
        raise RuntimeError(f"Could not extract text from {file_path}")
    if ocr:
        pages = _ocr_empty_pages(file_path, pages)
    return pages


# ── pdfplumber ──────────────────────────────────────────────────────────────
def _try_pdfplumber(file_path: str) -> Optional[List[PageText]]:
    try:
        import pdfplumber  # type: ignore
        pages: List[PageText] = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                try:
                    text = page.extract_text() or ""
                except Exception as e:
                    log.debug("pdfplumber page %d error: %s", i, e)
                    text = ""
                pages.append(PageText(i, text, _heading_from(text)))
        return pages
    except Exception as e:
        log.debug("pdfplumber failed for %s: %s", file_path, e)
        return None


# ── pypdf fallback ──────────────────────────────────────────────────────────
def _try_pypdf(file_path: str) -> Optional[List[PageText]]:
    try:
        from pypdf import PdfReader  # type: ignore
        pages: List[PageText] = []
        reader = PdfReader(file_path, strict=False)
        for i, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append(PageText(i, text, _heading_from(text)))
        return pages
    except Exception as e:
        log.debug("pypdf failed for %s: %s", file_path, e)
        return None


# ── OCR for empty pages ─────────────────────────────────────────────────────
def _ocr_empty_pages(file_path: str, pages: List[PageText]) -> List[PageText]:
    """Replace thin/empty pages with Tesseract OCR text."""
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        return pages

    empty_nums = [p.page_num for p in pages if len(p.text.strip()) < 50]
    if not empty_nums:
        return pages

    try:
        images = convert_from_path(file_path, dpi=200)
        result = list(pages)
        for p in result:
            if p.page_num in empty_nums:
                idx = p.page_num - 1
                if idx < len(images):
                    try:
                        ocr_text = pytesseract.image_to_string(images[idx])
                        result[idx] = PageText(p.page_num, ocr_text, _heading_from(ocr_text))
                    except Exception as e:
                        log.debug("OCR failed page %d: %s", p.page_num, e)
        return result
    except Exception as e:
        log.debug("OCR conversion failed: %s", e)
        return pages
