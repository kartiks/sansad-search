"""
Internet Archive _djvu.txt parser for LS/RS parliamentary records.

Consumes:
  - djvu_text: the text content of an IA {identifier}_djvu.txt file
    (OCR text pre-extracted by the Internet Archive; no local OCR performed)
  - metadata:  the parsed JSON from the IA metadata API at
    https://archive.org/metadata/{identifier}
    (the top-level "metadata" dict is passed in directly)

Maps IA custom eparlib_* fields:
  eparlib_document_url     → source_url (set here; overridden by orchestrator with
                             archive.org item URL per Non-Negotiable #9 v3.0)
  eparlib_date             → date (ISO; also parses 'D-Month-YYYY' / 'D-Mon-YYYY')
  eparlib_session_number   → session_number (int or Roman numeral I–XVII)
  eparlib_question_type    → proceeding_type ('Starred'/'Unstarred' → typed string)
  eparlib_question_number  → question_number (int)
  eparlib_members          → questioner_names (list; string split on comma or list)
  eparlib_relation_ministry → ministry
  lok_sabha_number         → lok_sabha_number (LS only; pre-parsed int set on the
                             DocumentRef metadata by InternetArchiveProvider; null
                             for RS — PRD v3.0)
  eparlib_title / title    → subject; also used for proceeding_type fallback

IA metadata fields may be strings or single-element lists; _get() handles both.
eparlib_members may be a list of strings; _get_list() returns all elements.

Returns None when djvu_text has no usable content.

Returned dict shape:
{
    "source":           "LS" | "RS",
    "proceeding_type":  str | None,
    "date":             "YYYY-MM-DD" | None,
    "session_name":     str | None,
    "session_number":   int | None,
    "sitting_number":   int | None,
    "question_number":  int | None,
    "questioner_names": list[str],
    "ministry":         str | None,
    "subject":          str | None,
    "source_url":       str | None,   # eparlib_document_url; overridden by orchestrator (Non-Neg #9 v3.0)
    "page_reference":   None,         # not applicable for IA text
    "volume":           None,         # not applicable for LS/RS
    "raw_text":         str,
}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# IA _djvu.txt page separator (form feed or IA-style page marker)
_PAGE_BREAK_RE = re.compile(r"(?m)\x0c|^-{4,}\s*$")

# ISO date validation
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Roman numeral → integer lookup (session numbers I–XVII)
_ROMAN_NUMERALS: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17,
}

# eparlib_question_type → proceeding_type
_QUESTION_TYPE_MAP: dict[str, str] = {
    "unstarred": "unstarred_question",
    "starred": "starred_question",
}

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


_EPARLIB_BASE = "https://eparlib.sansad.in"


def _normalize_eparlib_url(url: str | None) -> str | None:
    """Resolve relative eparlib URLs to absolute form.

    IA metadata sometimes stores eparlib_document_url as a root-relative path
    (e.g. '/handle/123456789/4') instead of a full URL.  Prepending the known
    base makes these safe to use as href values.
    """
    if url is None:
        return None
    if url.startswith("/"):
        return _EPARLIB_BASE + url
    return url


def _get(metadata: dict[str, Any], key: str) -> str | None:
    """Extract a metadata value that may be a string or a single-element list."""
    val = metadata.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return str(val)


def _get_list(metadata: dict[str, Any], key: str) -> list[str]:
    """Extract a metadata value as a list of strings.

    If the value is already a list, return all non-empty elements.
    If a string, split on semicolon (the eparlib_members delimiter) and
    canonicalize each element: strip leading/trailing whitespace and collapse
    internal whitespace runs to a single space.
    """
    val = metadata.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return [" ".join(str(item).split()) for item in val if str(item).strip()]
    raw = str(val).strip()
    if not raw:
        return []
    return [" ".join(part.split()) for part in raw.split(";") if part.strip()]


def _parse_eparlib_date(date_str: str) -> str | None:
    """Parse eparlib_date to ISO YYYY-MM-DD.

    Accepts ISO format directly, or 'D-Mon-YYYY' / 'D-Month-YYYY' (e.g.
    '15-Mar-2023', '15-March-2023'). Returns None for unrecognised formats.
    """
    if _ISO_DATE_RE.match(date_str):
        return date_str
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    logger.warning(
        "IA metadata eparlib_date %r is not a recognised format; ignoring", date_str
    )
    return None


def _infer_proceeding_type_from_type_field(question_type: str | None) -> str | None:
    """Map eparlib_question_type to proceeding_type. None if absent or unrecognised."""
    if not question_type:
        return None
    return _QUESTION_TYPE_MAP.get(question_type.strip().lower())


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

    source_url = _normalize_eparlib_url(_get(metadata, "eparlib_document_url"))

    # Issue 1: parse 'D-Mon-YYYY' / 'D-Month-YYYY' in addition to ISO
    date_raw = _get(metadata, "eparlib_date")
    date_str = _parse_eparlib_date(date_raw) if date_raw else None

    # Issue 2: session_number may be a Roman numeral (e.g. 'VIII')
    session_number_raw = _get(metadata, "eparlib_session_number")
    session_number: int | None = None
    if session_number_raw is not None:
        try:
            session_number = int(session_number_raw)
        except (ValueError, TypeError):
            session_number = _ROMAN_NUMERALS.get(session_number_raw.strip().upper())

    title = _get(metadata, "eparlib_title") or _get(metadata, "title")

    # Issue 3: eparlib_question_type takes precedence over title inference
    question_type = _get(metadata, "eparlib_question_type")
    proceeding_type = _infer_proceeding_type_from_type_field(question_type)
    if proceeding_type is None:
        proceeding_type = _infer_proceeding_type(title)

    # Issue 7: extract Q&A-specific eparlib fields
    question_number_raw = _get(metadata, "eparlib_question_number")
    question_number: int | None = None
    if question_number_raw is not None:
        try:
            question_number = int(question_number_raw)
        except (ValueError, TypeError):
            pass

    questioner_names: list[str] = _get_list(metadata, "eparlib_members")
    ministry: str | None = _get(metadata, "eparlib_relation_ministry")

    # PRD v3.0: lok_sabha_number is pre-parsed to an int by the IA provider and
    # is LS-only. RS records always carry null.
    lok_sabha_number = metadata.get("lok_sabha_number") if source == "LS" else None

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": date_str,
        "session_name": None,       # resolved later by sessions.py canonicalizer
        "session_number": session_number,
        "sitting_number": None,     # not available in IA metadata
        "question_number": question_number,
        "questioner_names": questioner_names,
        "ministry": ministry,
        "subject": title[:500] if title else None,
        "source_url": source_url,
        "page_reference": None,     # IA text has no page numbers
        "volume": None,
        "time_of_day": None,        # IA pre-OCR text has no sitting start time
        "lok_sabha_number": lok_sabha_number,
        "raw_text": raw_text,
    }
