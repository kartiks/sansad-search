"""
HTML parser for parliamentary records from constitutionofindia.net (CA) and
sansad.in/rs (recent RS).

Converts raw HTML into raw record dicts for downstream segmenters. Does not
perform canonicalization or segmentation — it extracts structured text and
metadata.

Returned dict shape (fields may be None if not found in HTML):
{
    "source":           "LS" | "RS" | "CA",
    "proceeding_type":  str,
    "date":             "YYYY-MM-DD" | None,
    "session_name":     str | None,
    "session_number":   int | None,
    "sitting_number":   int | None,
    "subject":          str | None,
    "source_url":       str | None,
    "time_of_day":      str | None,   # HH:MM; HTML sources only; None for IA/PDF
    "raw_text":         str,
    "raw_html":         str,
    # CA only:
    "ca_speech_pairs":  list[tuple[str, str, str | None]] | None,
    #                   (speaker, text, subject_for_this_speech)
}
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

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

# HH:MM pattern for time_of_day extraction
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

# CSS classes that identify a coi speech grid row
_COI_GRID_CLASS = "lg:grid-cols-12"


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


def _extract_time_of_day(soup: BeautifulSoup) -> str | None:
    """
    Extract sitting start time as HH:MM from HTML.

    Looks for <time> elements first, then HH:MM patterns in header/metadata
    areas. Returns None if no valid time is found.

    BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 3):
    - CA (constitutionofindia.net): time_of_day present when a <time> element
      exists in the sitting page header. Not all CA pages expose this. When
      absent, time_of_day is None.
    - RS (sansad.in/rs): time_of_day may appear in sitting header metadata.
      Availability is inconsistent across sittings. When absent, None.
    - IA pre-OCR text and PDF sources: time_of_day is always None by design
      (set explicitly in ia_text_parser and pdf_parser). Finding: 2026-06-02.
    """
    # Check <time> element (most reliable when present)
    time_tag = soup.find("time")
    if time_tag:
        text = time_tag.get_text(strip=True)
        m = _TIME_RE.match(text)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                return f"{h:02d}:{mi:02d}"

    # Fall back: look for HH:MM in header/metadata class elements
    for tag in soup.find_all(class_=re.compile(r"time|header|meta", re.I)):
        text = tag.get_text()
        m = _TIME_RE.search(text)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                return f"{h:02d}:{mi:02d}"

    return None


def parse_html(
    html: str,
    source: str,
    source_url: str | None = None,
    proceeding_type_hint: str | None = None,
) -> dict[str, Any]:
    """
    Parse a single CA, LS, or RS HTML document into a raw record dict.

    Args:
        html:                  Raw HTML string.
        source:                "CA", "LS", or "RS".
        source_url:            URL the HTML was fetched from.
        proceeding_type_hint:  If the caller already knows the proceeding type
                               (e.g. from the URL pattern), pass it here.

    Returns:
        A raw record dict. The segmenters consume raw_text, raw_html, and
        ca_speech_pairs (CA only).
    """
    if source not in ("CA", "LS", "RS"):
        raise ValueError(f"Invalid source: {source!r}. Must be 'CA', 'LS', or 'RS'.")

    soup = BeautifulSoup(html, "lxml")

    # ── Metadata extraction ───────────────────────────────────────────────────

    title_tag = soup.find("title")
    title_text = _clean_text(title_tag.get_text()) if title_tag else ""

    h1_tag = soup.find("h1")
    h1_text = _clean_text(h1_tag.get_text()) if h1_tag else ""

    meta_text = f"{title_text} {h1_text}"

    # Date: look in title, h1, and common metadata divs (CA overrides this in orchestrator)
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

    # time_of_day: extract from HTML sources
    time_of_day = _extract_time_of_day(soup)

    # ── Body text extraction ──────────────────────────────────────────────────

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"content|main|body", re.I))
        or soup.find(class_=re.compile(r"content|main|body", re.I))
        or soup.body
        or soup
    )

    lines = main.get_text(separator="\n").splitlines()
    raw_text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in lines)
    raw_html = str(main)

    # CA records: no session names/numbers; extract structured speech pairs with subjects
    ca_speech_pairs: list[tuple[str, str, str | None]] | None = None
    if source == "CA":
        session_name = None
        session_number = None
        ca_speech_pairs = _extract_coi_speech_pairs_with_subjects(soup)

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": date_str,
        "session_name": session_name,
        "session_number": session_number,
        "sitting_number": sitting_number,
        "subject": subject,
        "source_url": source_url,
        "time_of_day": time_of_day,
        "raw_text": raw_text,
        "raw_html": raw_html,
        "ca_speech_pairs": ca_speech_pairs,
    }


# ── CA constitutionofindia.net DOM helpers ────────────────────────────────────


def _extract_coi_toc_first_item(soup: BeautifulSoup) -> str | None:
    """
    Extract the first item's text from the page TOC <ul>.

    The TOC contains <li><a href="#ID">Topic</a></li> items. The first item's
    text is used as the subject fallback when no section header precedes the
    first speech in the sitting.

    BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 2):
    The constitutionofindia.net TOC <li><a href="#ID"> anchor IDs do not
    consistently correspond to id= attributes on body elements in the observed
    HTML structure. The anchor href IDs in the TOC (#objectives-resolution,
    etc.) are present but the matching id= attributes on body section elements
    were not found reliably across all volumes. Therefore: TOC first-item link
    text is used directly as the subject fallback (not resolved via anchor
    mapping). This is the correct fallback per the PRD spec. Finding: 2026-06-02.
    """
    for ul in soup.find_all("ul"):
        first_li = ul.find("li")
        if not first_li:
            continue
        first_a = first_li.find("a", href=lambda h: h and h.startswith("#"))
        if first_a:
            return _clean_text(first_a.get_text())
    return None


def _is_coi_speech_row(element: Any) -> bool:
    """Return True if the element is a constitutionofindia.net speech grid row."""
    if not hasattr(element, "get"):
        return False
    classes = element.get("class") or []
    return _COI_GRID_CLASS in classes


def _extract_section_header_text(element: Any) -> str | None:
    """
    Return the text of a standalone bold section header, or None.

    Section headers are standalone bold elements (<strong>, <b>) or paragraphs
    containing only a single bold element. Bold speaker names are inside speech
    grid rows (which are excluded by the caller iterating wrapper children).
    """
    if not hasattr(element, "name") or not element.name:
        return None
    name = element.name.lower()

    if name in ("strong", "b"):
        text = _clean_text(element.get_text())
        if text and len(text) < 300:
            return text

    if name == "p":
        # Standalone paragraph containing only a single bold element
        bold_children = [
            c for c in element.children
            if hasattr(c, "name") and c.name in ("strong", "b")
        ]
        text_content = _clean_text(element.get_text())
        if bold_children and text_content and len(text_content) < 300:
            # Confirm the paragraph has no other substantial text outside the bold
            non_bold_text = "".join(
                str(c) for c in element.children
                if not (hasattr(c, "name") and c.name in ("strong", "b"))
            ).strip()
            if len(non_bold_text) < 5:
                return text_content

    return None


def _parse_speech_row_element(row: Tag) -> tuple[str, str] | None:
    """
    Extract (speaker_name, speech_text) from a constitutionofindia.net speech grid row.

    Row structure:
      div.lg:grid-cols-12
        div.lg:col-span-3  → ref number (span.bg-[#F8FFA3]) + speaker (span.font-medium)
        div.lg:col-span-9  → speech prose text
    """
    info_div = row.find("div", class_=lambda c: c and "lg:col-span-3" in c)
    content_div = row.find("div", class_=lambda c: c and "lg:col-span-9" in c)
    if not info_div or not content_div:
        return None

    # Only process rows with a reference number (yellow span)
    ref_span = info_div.find("span", class_=lambda c: c and "bg-[#F8FFA3]" in c)
    if not ref_span:
        return None

    # Speaker name: first non-ref span anywhere inside info_div.
    # The ref span is identified by bg-[#F8FFA3]; the speaker span may be
    # a direct child or nested one level deeper depending on site version.
    speaker = None
    for span in info_div.find_all("span"):
        span_classes = span.get("class") or []
        if any("bg-[#F8FFA3]" in c for c in span_classes):
            continue  # skip the yellow reference-number span
        name = span.get_text(strip=True)
        if name:
            speaker = name
            break

    if not speaker:
        return None

    text_lines = content_div.get_text(separator="\n").splitlines()
    text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text_lines).strip()
    if not text:
        return None

    return speaker, text


def _walk_ca_elements(node: Any):
    """Yield all descendant elements in document order, not descending into speech rows."""
    for child in node.children:
        if isinstance(child, NavigableString):
            continue
        if not hasattr(child, "name") or not child.name:
            continue
        yield child
        if not _is_coi_speech_row(child):
            yield from _walk_ca_elements(child)


def _extract_coi_speech_pairs_with_subjects(
    soup: BeautifulSoup,
) -> list[tuple[str, str, str | None]]:
    """
    Walk the constitutionofindia.net page DOM in document order.

    Tracks standalone bold section headers as the current subject. When a new
    section header is encountered, all subsequent speeches inherit that subject
    until the next header. If no section header precedes the first speech,
    falls back to the first TOC item's text.

    Returns a list of (speaker, text, subject) triples.

    BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 1 — CA):
    The constitutionofindia.net HTML structure (one page per sitting) exposes
    all debate speeches in a single ordered DOM. Speeches appear as
    lg:grid-cols-12 div elements. CA has no Q+A exchanges (no Question Hour
    in the Constituent Assembly), so the shared sequence space contains only
    speech records. Cross-type interleaving is not applicable for CA. The
    sitting-level sequence is reliably assignable from DOM order. Finding: 2026-06-02.
    """
    toc_first = _extract_coi_toc_first_item(soup)
    current_subject: str | None = toc_first
    pairs: list[tuple[str, str, str | None]] = []

    # Prefer the narrowest content container so page chrome (nav, footer, site
    # header) is excluded. The live site wraps speech rows in
    # page-debate-detail__content. Never use div.wrapper — the site header also
    # carries that class and appears earlier in the DOM than the content area.
    # <main> is a reliable fallback for modern pages; soup.body covers fixtures.
    wrapper = (
        soup.find("div", class_="page-debate-detail__content")
        or soup.find("main")
        or soup.body
        or soup
    )

    for child in _walk_ca_elements(wrapper):
        if _is_coi_speech_row(child):
            result = _parse_speech_row_element(child)
            if result:
                speaker, text = result
                pairs.append((speaker, text, current_subject))
            else:
                # Grid row with no ref span — on the live site, section headers
                # use the same lg:grid-cols-12 layout as speech rows but omit
                # the reference number span. Extract the header text from inside
                # the content column (lg:col-span-9).
                content_div = child.find(
                    "div", class_=lambda c: c and "lg:col-span-9" in c
                )
                if content_div:
                    for inner in content_div.children:
                        if isinstance(inner, NavigableString):
                            continue
                        header_text = _extract_section_header_text(inner)
                        if header_text:
                            current_subject = header_text
                            break
            continue

        header_text = _extract_section_header_text(child)
        if header_text:
            current_subject = header_text

    return pairs
