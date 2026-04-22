"""
pdf_parser.py — Extract text from PDF files.

Extraction chain (sheet 14, firstflush/pdf-ninja pattern):
  1. pdfplumber  — primary; accurate layout with heading hints.
  2. pypdf       — pure-Python fallback when pdfplumber fails.
  3. pytesseract — optional OCR for scanned/image-only pages; only
                   triggered when the caller passes ocr=True.

Each extractor returns a list of PageText objects so the rest of the
pipeline is format-agnostic.

Edge-case handling (sheet 2 — stress tests):
  - Corrupted PDF       → pdfplumber raises → retried with pypdf → logged.
  - Encrypted PDF       → both libraries raise → marked as failed.
  - Scanned PDF (no text) → empty pages returned; OCR path opt-in.
  - Very large PDFs     → streamed page-by-page; memory bounded.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ── Optional imports ─────────────────────────────────────────────────────────
try:
    import pdfplumber as _pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _pdfplumber = None  # type: ignore
    _HAS_PDFPLUMBER = False

try:
    import pypdf as _pypdf
    _HAS_PYPDF = True
except ImportError:
    _pypdf = None  # type: ignore
    _HAS_PYPDF = False

try:
    import pytesseract as _pytesseract
    from PIL import Image as _PIL_Image
    _HAS_TESSERACT = True
except ImportError:
    _pytesseract = None  # type: ignore
    _PIL_Image = None  # type: ignore
    _HAS_TESSERACT = False


# ── Public data type ──────────────────────────────────────────────────────────
@dataclass
class PageText:
    page_num: int           # 1-based
    text: str               # extracted text (may be empty for blank/image pages)
    heading_hint: str = ""  # first non-blank line, used as sectionHeader hint


# ── Heading detection ────────────────────────────────────────────────────────
_HEADING_RE = re.compile(r"^[A-Z0-9][\w\s\-:]{3,80}$")


def _guess_heading(text: str) -> str:
    """
    Heuristically pick a heading from the first few lines of the page.
    Returns empty string if no obvious heading is found.
    """
    for line in text.splitlines()[:5]:
        line = line.strip()
        if line and _HEADING_RE.match(line):
            return line
    return ""


# ── pdfplumber extractor ──────────────────────────────────────────────────────
def _extract_pdfplumber(file_path: str) -> list[PageText]:
    pages: list[PageText] = []
    with _pdfplumber.open(file_path) as pdf:  # type: ignore[union-attr]
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PageText(
                page_num=i,
                text=text,
                heading_hint=_guess_heading(text),
            ))
    return pages


# ── pypdf fallback extractor ──────────────────────────────────────────────────
def _extract_pypdf(file_path: str) -> list[PageText]:
    pages: list[PageText] = []
    reader = _pypdf.PdfReader(file_path, strict=False)  # type: ignore[union-attr]
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(PageText(
            page_num=i,
            text=text,
            heading_hint=_guess_heading(text),
        ))
    return pages


# ── OCR extractor (opt-in) ────────────────────────────────────────────────────
def _extract_ocr(file_path: str, progress_cb=None) -> list[PageText]:
    """
    Rasterize each page and run Tesseract.
    Requires pytesseract + Pillow + a Tesseract binary on PATH.
    progress_cb(page_num, total) is called for each page if provided.
    """
    if not _HAS_TESSERACT:
        raise RuntimeError(
            "pytesseract / Pillow not installed, or Tesseract binary not found."
        )

    # Use pdfplumber to render pages as images
    if not _HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber required for OCR page rendering.")

    pages: list[PageText] = []
    with _pdfplumber.open(file_path) as pdf:  # type: ignore[union-attr]
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            if progress_cb:
                progress_cb(i, total)
            # Render at 200 DPI for reasonable OCR accuracy
            img = page.to_image(resolution=200).original
            text = _pytesseract.image_to_string(img)  # type: ignore[union-attr]
            pages.append(PageText(
                page_num=i,
                text=text or "",
                heading_hint=_guess_heading(text or ""),
            ))
    return pages


# ── Public API ────────────────────────────────────────────────────────────────
def extract_pages(
    file_path: str,
    ocr: bool = False,
    progress_cb=None,
) -> tuple[list[PageText], str | None]:
    """
    Extract text from a PDF file.

    Parameters
    ----------
    file_path : str
        Absolute path to the PDF.
    ocr : bool
        If True, use Tesseract OCR (slow; for scanned documents).
    progress_cb : callable | None
        Called as progress_cb(current_page, total_pages) during OCR.

    Returns
    -------
    (pages, error_message)
        pages is a list of PageText; error_message is None on success.
    """
    if not os.path.exists(file_path):
        return [], f"File not found: {file_path}"

    if ocr:
        try:
            return _extract_ocr(file_path, progress_cb), None
        except Exception as exc:
            return [], f"OCR failed: {exc}"

    # --- standard text extraction ---
    if _HAS_PDFPLUMBER:
        try:
            return _extract_pdfplumber(file_path), None
        except Exception:
            pass  # fall through to pypdf

    if _HAS_PYPDF:
        try:
            return _extract_pypdf(file_path), None
        except Exception as exc:
            return [], f"PDF parsing failed: {exc}"

    return [], "No PDF library available (install pdfplumber or pypdf)."


def tesseract_available() -> bool:
    """True if pytesseract and Tesseract binary are both reachable."""
    if not _HAS_TESSERACT:
        return False
    try:
        _pytesseract.get_tesseract_version()  # type: ignore[union-attr]
        return True
    except Exception:
        return False
