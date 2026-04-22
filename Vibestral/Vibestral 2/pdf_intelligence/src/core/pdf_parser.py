# src/core/pdf_parser.py
# Changes: Merged Lovable + Claude; fixed all mojibake string literals;
# kept Lovable's Iterator-based API; added Claude's import-guard pattern.
"""PDF text extraction.

Strategy:
1. pdfplumber -- primary; accurate per-page text + heading detection.
2. pypdf      -- pure-Python fallback when pdfplumber fails.
3. pytesseract -- optional OCR for scanned pages; opt-in only.

Returns an iterator of PageText objects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)


@dataclass
class PageText:
    page_num: int           # 1-based
    text: str
    heading: Optional[str]  # best-effort section header for this page


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------
def _guess_heading(text: str) -> Optional[str]:
    """Cheap heading detection: first short ALL-CAPS or Title-Case line."""
    if not text:
        return None
    for line in text.splitlines()[:6]:
        s = line.strip()
        if 4 <= len(s) <= 80:
            words = s.split()
            if not words:
                continue
            if s.isupper():
                return s
            if all(w[:1].isupper() for w in words if w[:1].isalpha()):
                return s
    return None


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------
def _extract_pdfplumber(path: Path) -> Iterator[PageText]:
    import pdfplumber  # type: ignore
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            except Exception as e:
                log.warning("pdfplumber page %d failed: %s", i, e)
                txt = ""
            yield PageText(i, txt, _guess_heading(txt))


def _extract_pypdf(path: Path) -> Iterator[PageText]:
    from pypdf import PdfReader  # type: ignore
    reader = PdfReader(str(path), strict=False)
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            log.warning("pypdf page %d failed: %s", i, e)
            txt = ""
        yield PageText(i, txt, _guess_heading(txt))


_TESS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract() -> None:
    try:
        import pytesseract  # type: ignore
        import shutil
        if shutil.which("tesseract"):
            return
        for p in _TESS_PATHS:
            import os
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                return
    except Exception:
        pass


def _ocr_page(path: Path, page_index: int, dpi: int = 200) -> str:
    """OCR a single PDF page. Requires pytesseract + Tesseract binary on PATH."""
    try:
        import pytesseract  # type: ignore
        import pdfplumber   # type: ignore
        _configure_tesseract()
    except ImportError:
        return ""
    try:
        with pdfplumber.open(str(path)) as pdf:
            img = pdf.pages[page_index].to_image(resolution=dpi).original
            return pytesseract.image_to_string(img) or ""
    except Exception as e:
        log.warning("OCR page %d failed: %s", page_index + 1, e)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_pages(path: Path, ocr: bool = False) -> Iterator[PageText]:
    """Yield PageText for every page. Tries pdfplumber -> pypdf -> OCR (if asked)."""
    pages: list[PageText] = []
    last_error: Exception | None = None

    for fn, name in ((_extract_pdfplumber, "pdfplumber"),
                     (_extract_pypdf, "pypdf")):
        try:
            pages = list(fn(path))
            log.debug("Extracted %d pages via %s", len(pages), name)
            break
        except Exception as e:
            last_error = e
            log.warning("%s failed on %s: %s", name, path.name, e)
            pages = []

    if not pages and last_error:
        raise last_error

    if ocr:
        for p in pages:
            if not p.text.strip():
                p.text = _ocr_page(path, p.page_num - 1)

    yield from pages


def page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore
        return len(PdfReader(str(path), strict=False).pages)
    except Exception:
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(str(path)) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0


def tesseract_available() -> bool:
    """Cheap probe so the UI can grey-out the OCR button."""
    try:
        import pytesseract  # type: ignore
        _configure_tesseract()
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
