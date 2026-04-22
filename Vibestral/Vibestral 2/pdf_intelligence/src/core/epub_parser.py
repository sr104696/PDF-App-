# src/core/epub_parser.py
# Changes: Based on Claude's version which has epub_to_pdf(); fixed all mojibake;
# uses import guards for optional deps; returns Iterator[EpubChapter] like Lovable.
"""EPUB text extraction.

Pure-Python: ebooklib + BeautifulSoup. lxml used if available, else html.parser.
Each EPUB chapter is yielded as one "page" so the rest of the pipeline
(chunker, indexer, searcher) doesn't need to know it's not a PDF.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)

_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")

try:
    import ebooklib  # type: ignore
    from ebooklib import epub as _epub
    _HAS_EBOOKLIB = True
except ImportError:
    _HAS_EBOOKLIB = False
    _epub = None  # type: ignore

try:
    from bs4 import BeautifulSoup as _BS  # type: ignore
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
class EpubChapter:
    page_num: int           # synthetic -- chapter index (1-based)
    text: str
    heading: Optional[str]


def _parser_name() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except ImportError:
        return "html.parser"


def _html_to_text(html_bytes: bytes) -> tuple[str, str]:
    """Parse HTML bytes -> (plain_text, heading_hint)."""
    if not _HAS_BS4:
        raise ImportError("beautifulsoup4 is required to parse EPUB files.")
    for parser in ("lxml", "html.parser"):
        try:
            soup = _BS(html_bytes, parser)
            for tag in soup(["script", "style", "head", "meta", "link", "nav"]):
                tag.decompose()
            heading = ""
            h_tag = soup.find(["h1", "h2", "h3", "title"])
            if h_tag:
                heading = h_tag.get_text(strip=True)[:120]
            text = soup.get_text("\n", strip=True)
            text = _WS.sub(" ", text)
            text = _NL.sub("\n\n", text).strip()
            return text, heading
        except Exception:
            continue
    return "", ""


def extract_chapters(path: Path) -> Iterator[EpubChapter]:
    if not _HAS_EBOOKLIB:
        raise ImportError("ebooklib not installed; cannot parse EPUB.")
    if not _HAS_BS4:
        raise ImportError("beautifulsoup4 not installed; cannot parse EPUB.")

    book = _epub.read_epub(str(path), options={"ignore_ncx": True})
    idx = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        try:
            text, heading = _html_to_text(item.get_body_content())
        except Exception as e:
            log.warning("EPUB chapter parse failed: %s", e)
            continue
        if not text.strip():
            continue
        idx += 1
        if not heading:
            heading = os.path.splitext(os.path.basename(item.file_name))[0]
        yield EpubChapter(idx, text, heading[:120] or None)


def chapter_count(path: Path) -> int:
    try:
        return sum(1 for _ in extract_chapters(path))
    except Exception:
        return 0


def to_pdf(path: Path, out_pdf: Path) -> tuple[bool, str]:
    """Convert EPUB to a simple searchable PDF using reportlab.
    Returns (success, message)."""
    if not _HAS_REPORTLAB:
        return False, "reportlab not installed; cannot generate PDF."
    try:
        chapters = list(extract_chapters(path))
    except Exception as e:
        return False, str(e)
    try:
        c = _rl_canvas.Canvas(str(out_pdf), pagesize=_RL_A4)
        width, height = _RL_A4
        margin = 50
        line_h = 14
        font = "Helvetica"
        font_size = 10
        for ch in chapters:
            c.setFont(font, 14)
            c.drawString(margin, height - margin, ch.heading or f"Chapter {ch.page_num}")
            c.setFont(font, font_size)
            y = height - margin - 30
            for paragraph in ch.text.split("\n"):
                wrapped = _rl_split(paragraph, font, font_size, width - 2 * margin)
                for line in wrapped:
                    if y < margin + line_h:
                        c.showPage()
                        c.setFont(font, font_size)
                        y = height - margin
                    c.drawString(margin, y, line)
                    y -= line_h
                y -= 4
            c.showPage()
        c.save()
        return True, str(out_pdf)
    except Exception as e:
        return False, f"PDF generation failed: {e}"
