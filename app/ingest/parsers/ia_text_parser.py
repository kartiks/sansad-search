"""
Internet Archive _djvu.txt parser for LS/RS parliamentary records.

Consumes:
  - djvu_text: the text content of an IA {identifier}_djvu.txt file
    (OCR text pre-extracted by the Internet Archive; no local OCR performed)
  - metadata:  the parsed JSON from the IA metadata API at
    https://archive.org/metadata/{identifier}
    (the top-level "metadata" dict is passed in directly)

Maps IA custom eparlib_* fields:
  eparlib_document_url → source_url (canonical citation; never archive.org)
  eparlib_date         → date
  eparlib_session_number → session_number
  eparlib_lok_sabha_number → (ignored here; used by corpus orchestrator)
  eparlib_title / title → subject

IA metadata fields may be strings or single-element lists; _get() handles both.

Returns None when djvu_text has no usable content.

Returned dict shape:
{
    "source":          "LS" | "RS",
    "proceeding_type": str | None,
    "date":            "YYYY-MM-DD" | None,
    "session_name":    str | None,
    "session_number":  int | None,
    "sitting_number":  int | None,
    "subject":         str | None,
    "source_url":      str | None,   # eparlib_document_url; never archive.org
    "page_reference":  None,         # not applicable for IA text
    "volume":          None,         # not applicable for LS/RS
    "raw_text":        str,
}
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# IA _djvu.txt page separator (form feed or IA-style page marker)
_PAGE_BREAK_RE = re.compile(r"(?m)\x0c|^-{4,}\s*$")

# ISO date validation
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Proceeding type hints from IA/eparlib titles
_TITLE_TYPE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"unstarred\s+question", re.IGNORECASE), "unstarred_question"),
    (re.compile(r"starred\s+question", re.IGNORECASE), "starred_question"),
    (re.compile(r"zero\s+hour", re.IGNORECASE), "zero_hour"),
    (re.compile(r"short\s+duration", re.IGNORECASE), "short_duration_discussion"),
    (re.compile(r"calling\s+attention", re.IGNORECASE), "calling_attention"),
    (re.compile(r"adjournment\s+motion", re.IGNORECASE), "adjournment_motion"),
    (re.compile(r"private\s+member", re.IGNORECASE), "private_member_bill"),
    (re.compile(r"short\s+notice", re.IGNORECASE), "short_notice_question"),
    (re.compile(r"debate|discussion|bill", re.IGNORECASE), "debate"),
]


def _get(metadata: dict[str, Any], key: str) -> str | None:
    """Extract a metadata value that may be a string or a single-element list."""
    val = metadata.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return str(val)


def _infer_proceeding_type(title: str | None) -> str | None:
    if not title:
        return None
    for pattern, ptype in _TITLE_TYPE_MAP:
        if pattern.search(title):
            return ptype
    return None


def _clean_djvu_text(raw: str) -> str:
    """Strip IA _djvu.txt structural markers; return clean plain text."""
    # Remove IA page-position markers like "\n \n" runs and form feeds
    text = _PAGE_BREAK_RE.sub("\n\n", raw)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_ia_text(
    djvu_text: str | bytes,
    metadata: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    """
    Parse an IA _djvu.txt file and its metadata JSON into a raw record dict.

    Args:
        djvu_text: Text content of the {identifier}_djvu.txt file.
        metadata:  The "metadata" dict from the IA metadata API response.
        source:    "LS" or "RS".

    Returns None if djvu_text contains no usable text.
    """
    if source not in ("LS", "RS"):
        raise ValueError(f"ia_text_parser supports only LS and RS; got {source!r}")

    if isinstance(djvu_text, bytes):
        djvu_text = djvu_text.decode("utf-8", errors="replace")

    raw_text = _clean_djvu_text(djvu_text)
    if not raw_text:
        logger.warning(
            "IA _djvu.txt has no usable content (source=%s, doc_url=%s); skipping",
            source,
            _get(metadata, "eparlib_document_url") or "<unknown>",
        )
        return None

    # ── Metadata mapping ──────────────────────────────────────────────────────

    source_url = _get(metadata, "eparlib_document_url")

    date_str = _get(metadata, "eparlib_date")
    if date_str and not _ISO_DATE_RE.match(date_str):
        logger.warning("IA metadata eparlib_date %r is not ISO format; ignoring", date_str)
        date_str = None

    session_number_raw = _get(metadata, "eparlib_session_number")
    session_number: int | None = None
    if session_number_raw is not None:
        try:
            session_number = int(session_number_raw)
        except (ValueError, TypeError):
            pass

    title = _get(metadata, "eparlib_title") or _get(metadata, "title")
    proceeding_type = _infer_proceeding_type(title)

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": date_str,
        "session_name": None,    # resolved later by sessions.py canonicalizer
        "session_number": session_number,
        "sitting_number": None,  # not available in IA metadata
        "subject": title[:500] if title else None,
        "source_url": source_url,
        "page_reference": None,  # IA text has no page numbers
        "volume": None,
        "raw_text": raw_text,
    }
