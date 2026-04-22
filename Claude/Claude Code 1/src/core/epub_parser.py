"""
epub_parser.py — Extract text from EPUB files.

Uses ebooklib + BeautifulSoup (html.parser fallback if lxml absent).
Each EPUB document item becomes one "page" (chapter).

Edge cases handled:
  - <script> / <style> tags stripped before get_text().
  - Chapters that fail to parse are skipped (not the whole book).
  - EPUB with broken HTML: BeautifulSoup html.parser is permissive.
  - Optional PDF generation via reportlab (no wkhtmltopdf dependency).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    import ebooklib
    from ebooklib import epub as _epub
    _HAS_EBOOKLIB = True
except ImportError:
    _HAS_EBOOKLIB = False
    _epub = None  # type: ignore

try:
    from bs4 import BeautifulSoup as _BS
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False
    _BS = None  # type: ignore

try:
    import reportlab  # noqa: F401
    from reportlab.pdfgen import canvas as _rl_canvas
    from reportlab.lib.pagesizes import A4 as _RL_A4
    from reportlab.lib.utils import simpleSplit as _rl_split
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False


@dataclass
class PageText:
    page_num: int           # chapter index (1-based)
    text: str
    heading_hint: str = ""  # chapter title if available


def _html_to_text(html_bytes: bytes) -> tuple[str, str]:
    """
    Parse HTML bytes → plain text.
    Returns (text, heading_hint).
    Tries lxml first, falls back to html.parser.
    """
    if not _HAS_BS4:
        raise ImportError("beautifulsoup4 is required to parse EPUB files.")

    for parser in ("lxml", "html.parser"):
        try:
            soup = _BS(html_bytes, parser)
            # Strip non-content tags
            for tag in soup(["script", "style", "head", "meta", "link"]):
                tag.decompose()
            # Try to extract chapter title
            heading = ""
            h_tag = soup.find(["h1", "h2", "h3", "title"])
            if h_tag:
                heading = h_tag.get_text(strip=True)[:120]
            text = soup.get_text(separator="\n", strip=True)
            return text, heading
        except Exception:
            continue
    return "", ""


def extract_pages(file_path: str) -> tuple[list[PageText], str | None]:
    """
    Extract text from an EPUB file.

    Returns (pages, error_message). error_message is None on success.
    """
    if not _HAS_EBOOKLIB:
        return [], "ebooklib not installed; cannot parse EPUB."
    if not _HAS_BS4:
        return [], "beautifulsoup4 not installed; cannot parse EPUB."
    if not os.path.exists(file_path):
        return [], f"File not found: {file_path}"

    try:
        book = _epub.read_epub(file_path, options={"ignore_ncx": True})
    except Exception as exc:
        return [], f"Failed to open EPUB: {exc}"

    pages: list[PageText] = []
    chapter_num = 1

    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        try:
            text, heading = _html_to_text(item.get_body_content())
        except Exception:
            continue  # skip broken chapter; don't abort whole book

        if not text.strip():
            continue

        # Use spine title if available, else our heading guess
        if not heading:
            heading = os.path.splitext(os.path.basename(item.file_name))[0]

        pages.append(PageText(
            page_num=chapter_num,
            text=text,
            heading_hint=heading[:120],
        ))
        chapter_num += 1

    return pages, None


def epub_to_pdf(epub_path: str, output_path: str, progress_cb=None) -> tuple[bool, str]:
    """
    Convert EPUB to a simple PDF using reportlab.
    Returns (success, message).
    Uses a fixed-width font so no font-file dependencies are needed.
    """
    if not _HAS_REPORTLAB:
        return False, "reportlab not installed; cannot generate PDF."

    pages, err = extract_pages(epub_path)
    if err:
        return False, err

    try:
        c = _rl_canvas.Canvas(output_path, pagesize=_RL_A4)
        width, height = _RL_A4
        margin = 50
        line_h = 14
        font = "Helvetica"
        font_size = 10

        total = len(pages)
        for idx, page in enumerate(pages, start=1):
            if progress_cb:
                progress_cb(idx, total)
            c.setFont(font, 14)
            c.drawString(margin, height - margin, page.heading_hint or f"Chapter {page.page_num}")
            c.setFont(font, font_size)
            y = height - margin - 30
            for paragraph in page.text.split("\n"):
                wrapped = _rl_split(paragraph, font, font_size, width - 2 * margin)
                for line in wrapped:
                    if y < margin + line_h:
                        c.showPage()
                        c.setFont(font, font_size)
                        y = height - margin
                    c.drawString(margin, y, line)
                    y -= line_h
                y -= 4  # paragraph gap
            c.showPage()

        c.save()
        return True, output_path
    except Exception as exc:
        return False, f"PDF generation failed: {exc}"
