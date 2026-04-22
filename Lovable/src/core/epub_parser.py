"""EPUB → text extraction.

Pure-Python: ebooklib + BeautifulSoup. lxml used if available, else html.parser.
We don't bundle wkhtmltopdf or pandoc — too large. If the user wants a PDF
of the EPUB, we generate one with reportlab from extracted text.

Each EPUB chapter is yielded as one "page" so the rest of the pipeline (chunker,
indexer, searcher) doesn't need to know it's not a PDF.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)

_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")


@dataclass
class EpubChapter:
    page_num: int          # synthetic — chapter index
    text: str
    heading: Optional[str]


def _parser_name() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except ImportError:
        return "html.parser"


def extract_chapters(path: Path) -> Iterator[EpubChapter]:
    import ebooklib  # type: ignore
    from ebooklib import epub  # type: ignore
    from bs4 import BeautifulSoup  # type: ignore

    book = epub.read_epub(str(path))
    parser = _parser_name()
    idx = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        idx += 1
        try:
            soup = BeautifulSoup(item.get_content(), parser)
        except Exception as e:
            log.warning("EPUB chapter parse failed: %s", e)
            continue

        # Strip noisy tags before pulling text.
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        heading = None
        h = soup.find(["h1", "h2", "h3"])
        if h:
            heading = h.get_text(" ", strip=True)[:120] or None

        text = soup.get_text("\n", strip=True)
        text = _WS.sub(" ", text)
        text = _NL.sub("\n\n", text).strip()
        if text:
            yield EpubChapter(idx, text, heading)


def chapter_count(path: Path) -> int:
    try:
        return sum(1 for _ in extract_chapters(path))
    except Exception:
        return 0


def to_pdf(path: Path, out_pdf: Path) -> None:
    """Optional: dump extracted EPUB text into a simple, searchable PDF."""
    from reportlab.lib.pagesizes import LETTER  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak  # type: ignore

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_pdf), pagesize=LETTER,
                            leftMargin=54, rightMargin=54,
                            topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    story = []
    for ch in extract_chapters(path):
        if ch.heading:
            story.append(Paragraph(ch.heading, styles["Heading2"]))
            story.append(Spacer(1, 8))
        for para in ch.text.split("\n\n"):
            para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if para.strip():
                story.append(Paragraph(para, styles["BodyText"]))
                story.append(Spacer(1, 6))
        story.append(PageBreak())
    doc.build(story)
