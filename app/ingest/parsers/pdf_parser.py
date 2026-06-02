"""
PDF parser for LS/RS DSpace PDF records.

Uses PyMuPDF (fitz) for embedded text extraction only. No OCR fallback.
A PDF with no embedded text layer is logged and skipped (returns None).
This matches the F01 spec: 2014+ DSpace PDFs are digital-born and will
have an embedded text layer; text-less PDFs are unparseable and skipped.

Returned dict shape (None when the PDF has no usable text):
{
    "source":             "LS" | "RS",
    "proceeding_type":    str,
    "date":               "YYYY-MM-DD" | None,
    "session_name":       str | None,
    "session_number":     int | None,
    "sitting_number":     int | None,
    "subject":            str | None,
    "volume":             int | None,
    "source_url":         str | None,
    "page_reference":     int | None,
    "raw_text":           str,
    "pages":              list[dict],
}

Each entry in pages:
{
    "page_num": int,   # 1-based
    "text":     str,
}
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Minimum character count to consider a page as having embedded text
_MIN_EMBEDDED_CHARS = 50

_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if m:
        try:
            d = date(int(m.group(3)), _MONTH_MAP[m.group(2).lower()], int(m.group(1)))
            return d.isoformat()
        except ValueError:
            return None
    return None


def parse_pdf(
    pdf_source: bytes | str | Path,
    source: str,
    source_url: str | None = None,
    volume: int | None = None,
    proceeding_type_hint: str | None = None,
) -> dict[str, Any] | None:
    """
    Parse a PDF document into a raw record dict using embedded text only.

    Returns None when the PDF has no extractable text (logged as a skip).

    Args:
        pdf_source:            PDF bytes, file path string, or Path.
        source:                "CA", "LS", or "RS".
        source_url:            URL the PDF was fetched from.
        volume:                CA volume number (1–12), if applicable.
        proceeding_type_hint:  Proceeding type if known from URL/context.
    """
    if source not in ("CA", "LS", "RS"):
        raise ValueError(f"Invalid source: {source!r}")

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    pages_out: list[dict] = []

    for i, page in enumerate(doc):
        page_num = i + 1
        text = page.get_text("text")
        if len(text.strip()) >= _MIN_EMBEDDED_CHARS:
            pages_out.append({"page_num": page_num, "text": text})

    doc.close()

    raw_text = "\n".join(p["text"] for p in pages_out)

    if not raw_text.strip():
        logger.warning(
            "PDF has no embedded text layer (%s source=%s); skipping",
            source_url or "<unknown>",
            source,
        )
        return None

    first_page_text = pages_out[0]["text"] if pages_out else ""
    date_str = _parse_date(first_page_text)

    lines = [ln.strip() for ln in first_page_text.splitlines() if ln.strip()]
    subject: str | None = lines[0][:500] if lines else None

    proceeding_type = proceeding_type_hint or "debate"

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": date_str,
        "session_name": None,
        "session_number": None,
        "sitting_number": None,
        "subject": subject,
        "volume": volume,
        "source_url": source_url,
        "page_reference": 1,
        "time_of_day": None,  # PDF sources have no sitting start time
        "raw_text": raw_text,
        "pages": pages_out,
    }
