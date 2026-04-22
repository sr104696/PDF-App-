"""
PDF text extraction with OCR fallback, plus EPUB extraction.
"""
import os
from typing import List, Tuple, Dict

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except Exception:
    HAS_PDFPLUMBER = False

try:
    import pypdf
    HAS_PYPDF = True
except Exception:
    HAS_PYPDF = False

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except Exception:
    HAS_TESSERACT = False

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    HAS_EPUB = True
except Exception:
    HAS_EPUB = False

# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def extract_pdf_text(file_path: str) -> Tuple[List[str], Dict]:
    pages: List[str] = []
    meta: Dict = {"title": "", "author": "", "pages": 0}

    # Primary: pdfplumber
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(file_path) as pdf:
                meta["pages"] = len(pdf.pages)
                m = pdf.metadata or {}
                meta["title"] = m.get("Title") or os.path.basename(file_path)
                meta["author"] = m.get("Author") or ""
                for p in pdf.pages:
                    txt = p.extract_text() or ""
                    pages.append(txt)
            return pages, meta
        except Exception:
            pass

    # Fallback: pypdf
    if HAS_PYPDF:
        reader = pypdf.PdfReader(file_path)
        meta["pages"] = len(reader.pages)
        m = reader.metadata or {}
        meta["title"] = m.get("/Title") or os.path.basename(file_path)
        meta["author"] = m.get("/Author") or ""
        for p in reader.pages:
            pages.append(p.extract_text() or "")
        return pages, meta

    raise RuntimeError("No PDF backend available (install pdfplumber or pypdf)")

def has_extractable_text(file_path: str) -> bool:
    """Heuristic: check first 3 pages for meaningful text."""
    if not HAS_PDFPLUMBER:
        return False
    try:
        with pdfplumber.open(file_path) as pdf:
            for p in pdf.pages[:3]:
                if len((p.extract_text() or "").strip()) > 100:
                    return True
        return False
    except Exception:
        return False

def ocr_pdf(file_path: str, lang: str = "eng", progress_callback=None) -> List[str]:
    if not HAS_TESSERACT:
        raise RuntimeError("pytesseract is not installed.")
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber is required for OCR rasterization.")

    pages: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            if progress_callback:
                progress_callback(f"OCR page {i+1}/{total}", int((i+1)/total*100))
            im = page.to_image(resolution=200).original
            text = pytesseract.image_to_string(im, lang=lang)
            pages.append(text)
    return pages

# ---------------------------------------------------------------------------
# EPUB
# ---------------------------------------------------------------------------
def extract_epub_text(file_path: str) -> Tuple[List[str], Dict]:
    if not HAS_EPUB:
        raise RuntimeError("ebooklib and beautifulsoup4 are required for EPUB.")
    book = epub.read_epub(file_path)
    title = book.get_metadata('DC', 'title')
    author = book.get_metadata('DC', 'creator')
    meta = {
        "title": title[0][0] if title else os.path.basename(file_path),
        "author": author[0][0] if author else "",
        "pages": 0,
    }
    chapters: List[str] = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            txt = soup.get_text(separator='\n', strip=True)
            if txt:
                chapters.append(txt)
    meta["pages"] = len(chapters)
    return chapters, meta
