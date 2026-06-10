"""
Parser for pre-extracted plain-text content from elibrary.sansad.in DSpace 7.

Each item in the "Text of Debates (English)" collection has a TEXT bundle
containing a Tika-extracted .pdf.txt file.  That file is fetched by the
ElibraryDSpace7Provider and passed here for structuring.

Unlike the IA text parser (which derives date/session from eparlib_* metadata),
this parser trusts the DSpace 7 API metadata already resolved by the provider
(dc.date.issued, dc.identifier.loksabhanumber, dc.identifier.sessionnumber).
No regex-based extraction of date or session is needed — the API values are
authoritative.

Returned dict shape (None when the text has no usable content):
{
    "source":           "LS",
    "proceeding_type":  "debate",
    "date":             "YYYY-MM-DD" | None,
    "session_name":     None,          # not derivable without a session calendar
    "session_number":   int | None,    # converted from Roman numeral if needed
    "lok_sabha_number": int | None,
    "sitting_number":   None,
    "question_number":  None,
    "questioner_names": [],
    "ministry":         None,
    "subject":          None,
    "source_url":       None,          # overridden by orchestrator (Non-Neg #9 v3.0)
    "page_reference":   None,
    "volume":           None,
    "raw_text":         str,
    "lang_original":    "en",
}
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Roman-numeral → int table for Lok Sabha session numbers (I through XX).
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
}

# Minimum character count to consider the extracted text usable.
_MIN_TEXT_CHARS = 100


def _parse_session_number(value: Any) -> int | None:
    """
    Convert a session number value to int.
    Accepts plain integers, numeric strings, or Roman numeral strings (I–XX).
    Returns None when the value is absent or unparseable.
    """
    if value is None:
        return None
    s = str(value).strip().upper()
    # Try plain integer
    try:
        return int(s)
    except ValueError:
        pass
    # Try Roman numeral
    return _ROMAN_TO_INT.get(s)


def _parse_lok_sabha_number(value: Any) -> int | None:
    """Parse the Lok Sabha number to int. Returns None when absent or invalid."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_elibrary_text(
    text: str,
    metadata: dict[str, Any],
    source: str = "LS",
) -> dict[str, Any] | None:
    """
    Structure a Tika-extracted plain-text debate transcript from elibrary.sansad.in.

    Args:
        text:     Raw plain-text content of the debate (from the DSpace 7 TEXT bundle).
        metadata: Provider-resolved metadata dict with keys:
                    "date"             – ISO date string "YYYY-MM-DD" (dc.date.issued)
                    "lok_sabha_number" – int | None (dc.identifier.loksabhanumber)
                    "session_number"   – int | None (already parsed by provider)
        source:   Corpus identifier — always "LS" for this parser.

    Returns:
        Structured raw-record dict, or None if the text is too short to be useful.
    """
    if not text or len(text.strip()) < _MIN_TEXT_CHARS:
        logger.warning("elibrary_text_parser: text too short; skipping")
        return None

    date_val = metadata.get("date")
    lok_sabha_number = _parse_lok_sabha_number(metadata.get("lok_sabha_number"))
    session_number = _parse_session_number(metadata.get("session_number"))

    return {
        "source": source,
        "proceeding_type": "debate",
        "date": date_val,
        # session_name is not derivable from session number alone (the actual
        # name — "Budget Session", "Monsoon Session", etc. — requires a session
        # calendar lookup that is outside the scope of this parser).
        "session_name": None,
        "session_number": session_number,
        "lok_sabha_number": lok_sabha_number,
        "sitting_number": None,
        "question_number": None,
        "questioner_names": [],
        "ministry": None,
        "subject": None,
        # source_url is overridden by the LS orchestrator with doc_ref.citation_url
        # (Non-Negotiable #9 v3.0: elibrary handle URL is canonical).
        "source_url": None,
        "page_reference": None,
        "volume": None,
        "raw_text": text,
        "lang_original": "en",
        "time_of_day": None,
        "word_count": None,
    }
