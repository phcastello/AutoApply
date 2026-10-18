"""Document text extraction for PDF, DOCX, TXT, and MD files.

Implements: TASK-030 M1 — extract raw text from uploaded career documents
for subsequent LLM-based knowledge base extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


def extract_text(file_path: Path) -> str:
    """Extract plain text from an uploaded document.

    Args:
        file_path: Path to the document file.

    Returns:
        Extracted plain text content.

    Raises:
        ValueError: If the file type is unsupported.
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".pdf":
        return _extract_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _extract_from_docx(file_path)
    else:  # .txt, .md
        return _extract_from_text(file_path)


def _extract_from_pdf(file_path: Path) -> str:
    """Extract text from a PDF file using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise RuntimeError(
            "PyPDF2 is required for PDF extraction. Install with: pip install PyPDF2"
        )

    reader = PdfReader(str(file_path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())

    result = "\n\n".join(pages)
    if not result.strip():
        logger.warning("PDF extraction yielded empty text: %s", file_path.name)
    return result


def _extract_from_docx(file_path: Path) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "python-docx is required for DOCX extraction. Install with: pip install python-docx"
        )

    doc = Document(str(file_path))
    paragraphs: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    result = "\n\n".join(paragraphs)
    if not result.strip():
        logger.warning("DOCX extraction yielded empty text: %s", file_path.name)
    return result


def _extract_from_text(file_path: Path) -> str:
    """Read a plain text or markdown file."""
    try:
        return file_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for %s, trying latin-1", file_path.name)
        return file_path.read_text(encoding="latin-1")


def extract_import_text(file_path: Path) -> str:
    """Preserve Word heading levels and contact tables for profile import only."""
    if file_path.suffix.lower() != ".docx":
        return extract_text(file_path)
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(file_path))
    parts = []
    for element in doc.element.body:
        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, doc)
            value = paragraph.text.strip()
            if not value:
                continue
            style = paragraph.style.name if paragraph.style else ""
            import re

            level = re.search(r"(?:Heading|Título)\s*(\d)", style, re.I)
            if level:
                value = "#" * min(6, int(level[1]) + 1) + " " + value
            parts.append(value)
        elif element.tag.endswith("}tbl"):
            for row in Table(element, doc).rows:
                cells = list(dict.fromkeys(c.text.strip() for c in row.cells if c.text.strip()))
                if len(cells) == 2:
                    parts.append(cells[0].rstrip(":") + ": " + cells[1])
                else:
                    parts.extend(cells)
    return "\n\n".join(parts)
