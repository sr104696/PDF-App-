"""PDF text extraction.

Strategy (sheet 14, v2):
1. Try pdfplumber for accurate per-page text + simple heading detection.
2. On failure or empty text, fall back to pypdf.
3. If still empty AND OCR is requested AND pytesseract+Tesseract are available,
   rasterize pages and OCR them. OCR is opt-in (sheet 4 "Make Searchable" button).

Returns an iterator of (page_number, page_text, heading_hint).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)


@dataclass
class PageText:
    page_num: int          # 1-based
    text: str
    heading: Optional[str]  # best-effort section header for this page


# ---------- primary: pdfplumber ----------------------------------------
def _extract_pdfplumber(path: Path) -> Iterator[PageText]:
    import pdfplumber  # type: ignore
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            except Exception as e:
                log.warning("pdfplumber page %d failed: %s", i, e)
                txt = ""
            heading = _guess_heading(txt)
            yield PageText(i, txt, heading)


# ---------- fallback: pypdf --------------------------------------------
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


# ---------- optional OCR -----------------------------------------------
def _ocr_page(path: Path, page_index: int, dpi: int = 200) -> str:
    """OCR a single PDF page. Requires pytesseract + Tesseract binary on PATH."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # noqa: F401
        import pdfplumber  # type: ignore
    except ImportError:
        return ""
    try:
        with pdfplumber.open(str(path)) as pdf:
            page = pdf.pages[page_index]
            img = page.to_image(resolution=dpi).original
            return pytesseract.image_to_string(img) or ""
    except Exception as e:
        log.warning("OCR page %d failed: %s", page_index + 1, e)
        return ""


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


# ---------- public API --------------------------------------------------
def extract_pages(path: Path, ocr: bool = False) -> Iterator[PageText]:
    """Yield PageText for every page. Tries pdfplumber → pypdf → OCR (if asked)."""
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
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
