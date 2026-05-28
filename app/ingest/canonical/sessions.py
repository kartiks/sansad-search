"""
Session name canonicalization.

Target format: "[Session Type] Session [Year]"
Multi-part sessions: "[Session Type] Session [Year] (Part N)"

CA records always return None regardless of any input session_name.

Examples:
  "Budget Session, 2023"              → "Budget Session 2023"
  "BUDGET SESSION 2023"               → "Budget Session 2023"
  "Monsoon Session 2022 (Part 2)"     → "Monsoon Session 2022 (Part 2)"
  "Winter Session, 2021 (Second Part)"→ "Winter Session 2021 (Part 2)"
  "Budget Session 2023 (Second Part)" → "Budget Session 2023 (Part 2)"
"""
from __future__ import annotations

import re
from typing import Optional

# Known session type keywords → canonical title-case form
_SESSION_TYPE_MAP: dict[str, str] = {
    "budget": "Budget",
    "monsoon": "Monsoon",
    "winter": "Winter",
    "special": "Special",
    "extraordinary": "Extraordinary",
}

# Ordinal words → integer
_ORDINAL_MAP: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10,
}

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Matches "(Second Part)", "(Part 2)", "(2nd Part)", "(3)", etc.
_PART_RE = re.compile(
    r"\(\s*"
    r"(?:"
    r"(?P<word>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
    r"(?:\s+part)?"
    r"|part\s*(?P<num1>\d+)"
    r"|(?P<num2>\d+)(?:st|nd|rd|th)?\s*part"
    r"|(?P<num3>\d+)"
    r")"
    r"\s*\)",
    re.IGNORECASE,
)


def _extract_year(text: str) -> Optional[str]:
    m = _YEAR_RE.search(text)
    return m.group(1) if m else None


def _extract_session_type(text: str) -> Optional[str]:
    lower = text.lower()
    for key, canonical in _SESSION_TYPE_MAP.items():
        if key in lower:
            return canonical
    # Fallback: capture the word immediately before "session"
    m = re.search(r"([A-Za-z]+)\s+session", text, re.IGNORECASE)
    if m:
        word = m.group(1)
        return word.title()
    return None


def _extract_part_number(text: str) -> Optional[int]:
    m = _PART_RE.search(text)
    if not m:
        return None
    if m.group("word"):
        return _ORDINAL_MAP.get(m.group("word").lower())
    for grp in ("num1", "num2", "num3"):
        if m.group(grp):
            try:
                return int(m.group(grp))
            except ValueError:
                pass
    return None


def canonicalize_session(
    session_name: Optional[str],
    source: str,
) -> Optional[str]:
    """
    Return the canonical session name string, or None for CA records.

    Args:
        session_name: Raw session name string from the source record.
        source:       "CA", "LS", or "RS".
    """
    if source == "CA":
        return None

    if not session_name or not session_name.strip():
        return None

    raw = session_name.strip()

    year = _extract_year(raw)
    session_type = _extract_session_type(raw)
    part_n = _extract_part_number(raw)

    # Build canonical string
    if session_type and year:
        canonical = f"{session_type} Session {year}"
    elif session_type:
        canonical = f"{session_type} Session"
    elif year:
        canonical = f"Session {year}"
    else:
        # Cannot parse — return title-cased version of original (best effort)
        canonical = raw.title()

    if part_n is not None:
        canonical += f" (Part {part_n})"

    return canonical
