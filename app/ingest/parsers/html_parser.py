"""
HTML parser for Lok Sabha and Rajya Sabha parliamentary records.

Converts raw HTML fetched from sansad.in / rajyasabha.gov.in into raw record
dicts. Each dict carries sufficient fields for the downstream segmenters to
produce Speech or Q+A exchange units. The parser does not perform
canonicalization or segmentation — it extracts structured text and metadata.

Returned dict shape (fields may be None if not found in the HTML):
{
    "source":           "LS" | "RS",
    "proceeding_type":  str,           # debate | starred_question | ...
    "date":             "YYYY-MM-DD" | None,
    "session_name":     str | None,
    "session_number":   int | None,
    "sitting_number":   int | None,
    "subject":          str | None,
    "source_url":       str | None,
    "raw_text":         str,           # full extracted text for segmenters
    "raw_html":         str,           # original HTML for segmenters needing structure
}
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Proceeding type labels as they appear in LS/RS HTML titles / metadata
_PROCEEDING_TYPE_MAP: dict[str, str] = {
    "debate": "debate",
    "general discussion": "debate",
    "budget discussion": "debate",
    "starred question": "starred_question",
    "starred questions": "starred_question",
    "unstarred question": "unstarred_question",
    "unstarred questions": "unstarred_question",
    "zero hour": "zero_hour",
    "short notice question": "short_notice_question",
    "calling attention": "calling_attention",
    "short duration discussion": "short_duration_discussion",
    "adjournment motion": "adjournment_motion",
    "private member bill": "private_member_bill",
    "private member's bill": "private_member_bill",
}

# Patterns for date extraction from title or metadata elements
_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_date(text: str) -> str | None:
    """Extract the first date found in text; return ISO string or None."""
    m = _ISO_DATE_RE.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_RE.search(text)
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP[m.group(2).lower()]
        year = int(m.group(3))
        try:
            d = date(year, month, day)
            return d.isoformat()
        except ValueError:
            return None
    return None


def _detect_proceeding_type(text: str) -> str:
    """Best-effort proceeding type detection from title/subject text.

    Iterates keys longest-first so "unstarred question" matches before
    "starred question", and "adjournment motion" before "debate".
    """
    lower = text.lower()
    for key in sorted(_PROCEEDING_TYPE_MAP, key=len, reverse=True):
        if key in lower:
            return _PROCEEDING_TYPE_MAP[key]
    return "debate"


def _extract_session_number(text: str) -> int | None:
    m = re.search(r"(\d+)(?:st|nd|rd|th)?\s+session", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_sitting_number(text: str) -> int | None:
    m = re.search(r"(\d+)(?:st|nd|rd|th)?\s+sitting", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _clean_text(text: str) -> str:
    """Collapse runs of whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def parse_html(
    html: str,
    source: str,
    source_url: str | None = None,
    proceeding_type_hint: str | None = None,
) -> dict[str, Any]:
    """
    Parse a single LS or RS HTML document into a raw record dict.

    Args:
        html:                  Raw HTML string.
        source:                "LS" or "RS".
        source_url:            URL the HTML was fetched from.
        proceeding_type_hint:  If the caller already knows the proceeding type
                               (e.g. from the URL pattern), pass it here.

    Returns:
        A raw record dict. The segmenters consume raw_text and raw_html.
    """
    if source not in ("CA", "LS", "RS"):
        raise ValueError(f"Invalid source: {source!r}. Must be 'CA', 'LS', or 'RS'.")

    soup = BeautifulSoup(html, "lxml")

    # ── Metadata extraction ───────────────────────────────────────────────────

    # Title candidates: <title>, <h1>, first heading-like element
    title_tag = soup.find("title")
    title_text = _clean_text(title_tag.get_text()) if title_tag else ""

    h1_tag = soup.find("h1")
    h1_text = _clean_text(h1_tag.get_text()) if h1_tag else ""

    meta_text = f"{title_text} {h1_text}"

    # Date: look in title, h1, and common metadata divs
    date_str: str | None = None
    for candidate in [title_text, h1_text]:
        date_str = _parse_date(candidate)
        if date_str:
            break

    if not date_str:
        for meta_div in soup.find_all(class_=re.compile(r"date|header|metadata", re.I)):
            date_str = _parse_date(meta_div.get_text())
            if date_str:
                break

    # Subject: prefer h1, fallback to title
    subject = h1_text or title_text or None

    # Session info
    session_name: str | None = None
    session_number: int | None = _extract_session_number(meta_text)
    sitting_number: int | None = _extract_sitting_number(meta_text)

    session_tag = soup.find(class_=re.compile(r"session", re.I))
    if session_tag:
        session_name = _clean_text(session_tag.get_text()) or None

    # Proceeding type
    if proceeding_type_hint:
        proceeding_type = proceeding_type_hint
    else:
        proceeding_type = _detect_proceeding_type(meta_text)

    # ── Body text extraction ──────────────────────────────────────────────────

    # Remove script, style, nav, header, footer noise
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Prefer a main content container
    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"content|main|body", re.I))
        or soup.find(class_=re.compile(r"content|main|body", re.I))
        or soup.body
        or soup
    )

    # Preserve newlines so segmenters can split on attribution lines.
    # Only collapse horizontal whitespace within each line.
    lines = main.get_text(separator="\n").splitlines()
    raw_text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in lines)
    raw_html = str(main)

    # CA records have no session names or session numbers per the PRD spec.
    # Also extract structured speech pairs from the constitutionofindia.net DOM.
    ca_speech_pairs: list[tuple[str, str]] | None = None
    if source == "CA":
        session_name = None
        session_number = None
        ca_speech_pairs = _extract_coi_speech_pairs(soup)

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": date_str,
        "session_name": session_name,
        "session_number": session_number,
        "sitting_number": sitting_number,
        "subject": subject,
        "source_url": source_url,
        "raw_text": raw_text,
        "raw_html": raw_html,
        "ca_speech_pairs": ca_speech_pairs,
    }


def _extract_coi_speech_pairs(soup: "BeautifulSoup") -> list[tuple[str, str]]:
    """
    Extract (speaker, text) pairs from constitutionofindia.net debate pages.

    The site renders each speech as a CSS grid row:
      div.lg:grid.lg:grid-cols-12
        div.lg:col-span-3  → ref number (span.bg-[#F8FFA3]) + speaker name (span.font-medium)
        div.lg:col-span-9  → speech prose text

    Returns a list of (speaker_name, speech_text) tuples in document order.
    """
    speech_rows = soup.find_all(
        "div",
        class_=lambda c: c and "lg:grid-cols-12" in c and "lg:grid" in c,
    )
    pairs: list[tuple[str, str]] = []
    for row in speech_rows:
        info_div = row.find("div", class_=lambda c: c and "lg:col-span-3" in c)
        content_div = row.find("div", class_=lambda c: c and "lg:col-span-9" in c)
        if not info_div or not content_div:
            continue

        # Only process rows that have a reference number (yellow span)
        ref_span = info_div.find("span", class_=lambda c: c and "bg-[#F8FFA3]" in c)
        if not ref_span:
            continue

        # Speaker name: the direct <span> child of info_div (not inside the ref wrapper div)
        speaker = None
        for child in info_div.children:
            if getattr(child, "name", None) == "span":
                name = child.get_text(strip=True)
                if name:
                    speaker = name
                    break

        if not speaker:
            continue

        text_lines = content_div.get_text(separator="\n").splitlines()
        text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text_lines).strip()
        if not text:
            continue

        pairs.append((speaker, text))

    return pairs
