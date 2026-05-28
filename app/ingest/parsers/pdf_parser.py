"""
PDF parser for Constituent Assembly debate volumes and LS/RS PDF records.

Uses PyMuPDF (fitz) for embedded text extraction. Falls back to Tesseract OCR
for pages that yield no embedded text (scanned pages). Sets ocr_low_confidence
flag when Tesseract confidence is below threshold.

Returned dict shape:
{
    "source":             "CA" | "LS" | "RS",
    "proceeding_type":    str,
    "date":               "YYYY-MM-DD" | None,
    "session_name":       str | None,
    "session_number":     int | None,
    "sitting_number":     int | None,
    "subject":            str | None,
    "volume":             int | None,     # CA only
    "source_url":         str | None,
    "page_reference":     int | None,     # first page of content
    "ocr_low_confidence": bool,
    "raw_text":           str,
    "pages":              list[dict],     # per-page breakdown for segmenters
}

Each entry in pages:
{
    "page_num":           int,   # 1-based
    "text":               str,
    "ocr":                bool,
    "ocr_confidence":     float | None,  # 0–100; None for non-OCR pages
}
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

OCR_CONFIDENCE_THRESHOLD = 60.0  # pages below this are flagged

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
        from datetime import date
        try:
            d = date(int(m.group(3)), _MONTH_MAP[m.group(2).lower()], int(m.group(1)))
            return d.isoformat()
        except ValueError:
            return None
    return None


def _ocr_page(page: fitz.Page) -> tuple[str, float]:
    """
    Run Tesseract OCR on a single PyMuPDF page.

    Returns (text, mean_confidence). Confidence is 0–100; -1.0 when pytesseract
    is unavailable or OCR fails entirely.
    """
    try:
        import pytesseract
        from PIL import Image

        mat = fitz.Matrix(2.0, 2.0)  # 2× scale for better OCR accuracy
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words = [
            (w, int(c))
            for w, c in zip(data["text"], data["conf"])
            if w.strip() and int(c) >= 0
        ]
        if not words:
            return "", -1.0

        text = " ".join(w for w, _ in words)
        confidence = sum(c for _, c in words) / len(words)
        return text, confidence

    except Exception as exc:
        logger.warning("OCR failed for page: %s", exc)
        return "", -1.0


def parse_pdf(
    pdf_source: bytes | str | Path,
    source: str,
    source_url: str | None = None,
    volume: int | None = None,
    proceeding_type_hint: str | None = None,
) -> dict[str, Any]:
    """
    Parse a PDF document into a raw record dict.

    Args:
        pdf_source:            PDF bytes, file path string, or Path.
        source:                "CA", "LS", or "RS".
        source_url:            URL the PDF was fetched from.
        volume:                CA volume number (1–12), if applicable.
        proceeding_type_hint:  Proceeding type if known from URL/context.

    Returns:
        Raw record dict. Segmenters consume raw_text and pages.
    """
    if source not in ("CA", "LS", "RS"):
        raise ValueError(f"Invalid source: {source!r}")

    # Open with PyMuPDF
    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    pages_out: list[dict] = []
    any_ocr_low_confidence = False

    for i, page in enumerate(doc):
        page_num = i + 1
        embedded_text = page.get_text("text")

        if len(embedded_text.strip()) >= _MIN_EMBEDDED_CHARS:
            pages_out.append({
                "page_num": page_num,
                "text": embedded_text,
                "ocr": False,
                "ocr_confidence": None,
            })
        else:
            # Scanned page — fall back to OCR
            ocr_text, confidence = _ocr_page(page)
            low_conf = confidence < OCR_CONFIDENCE_THRESHOLD if confidence >= 0 else True
            if low_conf:
                any_ocr_low_confidence = True
            pages_out.append({
                "page_num": page_num,
                "text": ocr_text,
                "ocr": True,
                "ocr_confidence": confidence if confidence >= 0 else None,
            })

    doc.close()

    raw_text = "\n".join(p["text"] for p in pages_out)

    # Best-effort metadata from first page text
    first_page_text = pages_out[0]["text"] if pages_out else ""
    date_str = _parse_date(first_page_text)
    subject: str | None = None

    # For CA, subject is typically the first non-blank line after the header
    lines = [ln.strip() for ln in first_page_text.splitlines() if ln.strip()]
    if lines:
        subject = lines[0][:500]

    proceeding_type = proceeding_type_hint or ("debate" if source == "CA" else "debate")

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
        "ocr_low_confidence": any_ocr_low_confidence,
        "raw_text": raw_text,
        "pages": pages_out,
    }
