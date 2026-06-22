"""
Search service for SansadSearch.

Responsibilities:
- Build Meilisearch filter expressions from structured filter input.
- Map sort selection to Meilisearch sort parameters.
- Call the Meilisearch parliamentary_records index.
- Format raw Meilisearch hits into API result dicts (snippet, date_display,
  proceeding_type_label, total_display).
- When debug=True: augment Meilisearch query with score/full-doc retrieval
  parameters; assemble and return the debug envelope (F10, PRD v3.0).
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ─────────────────────────────────────────────────────────────────

MEILI_INDEX_NAME = "parliamentary_records"
PER_PAGE = 20
MAX_TOTAL_HITS = 10000

# F02/F05 (PRD v3.3): configurable snippet size.
# The result-snippet crop window is sized per request from the optional
# `snippet_size` parameter, falling back to an operator-configurable default.
# NFR PERF-4 bounds the effective size to [20, 1000] words so PERF-1 holds at
# the maximum; the bound is enforced regardless of the operator default.
SNIPPET_SIZE_MIN = 20
SNIPPET_SIZE_MAX = 1000

# Built-in fallback default when SNIPPET_DEFAULT_WORDS is unset or itself invalid.
DEFAULT_SNIPPET_WORDS = 100


def _clamp_snippet_size(n: int) -> int:
    """Clamp *n* into the inclusive bound [SNIPPET_SIZE_MIN, SNIPPET_SIZE_MAX]."""
    return max(SNIPPET_SIZE_MIN, min(SNIPPET_SIZE_MAX, n))


def _operator_default_snippet_size() -> int:
    """
    Read the operator-configurable default snippet size from the
    SNIPPET_DEFAULT_WORDS environment variable (read per request so an operator
    env change takes effect on API restart with no code change).  Falls back to
    DEFAULT_SNIPPET_WORDS (100) when unset or not a valid integer string.
    """
    raw = os.environ.get("SNIPPET_DEFAULT_WORDS")
    if raw is None:
        return DEFAULT_SNIPPET_WORDS
    try:
        return int(raw)
    except (ValueError, TypeError):
        return DEFAULT_SNIPPET_WORDS


def resolve_effective_snippet_size(snippet_size: Any) -> int:
    """
    Resolve the effective snippet size (Meilisearch cropLength) for a request,
    per DATA-MODELS §2.3 "Effective snippet size".

    - A JSON integer is clamped into [20, 1000] (bounds inclusive; 0/negative/19
      → 20; 1001/5000 → 1000).
    - Anything else — absent (None), present-but-empty, non-numeric, a JSON float
      (non-integer numeric, e.g. 100.5), or a boolean — falls back to the
      operator-configurable default.
    - The result is always clamped into [20, 1000], so even an out-of-range
      operator default cannot violate NFR PERF-4.

    Note: ``bool`` is a subclass of ``int`` in Python, so JSON ``true``/``false``
    are explicitly treated as non-integers and fall back to the default.
    """
    if isinstance(snippet_size, bool):
        chosen = _operator_default_snippet_size()
    elif isinstance(snippet_size, int):
        chosen = snippet_size
    else:
        chosen = _operator_default_snippet_size()
    return _clamp_snippet_size(chosen)

_PROCEEDING_TYPE_LABELS: Dict[str, str] = {
    "debate": "Debate",
    "zero_hour": "Zero Hour",
    "short_duration_discussion": "Short Duration Discussion",
    "calling_attention": "Calling Attention",
    "adjournment_motion": "Adjournment Motion",
    "private_member_bill": "Private Member Bill",
    "short_notice_question": "Short Notice Question",
    "starred_question": "Starred Question",
    "unstarred_question": "Unstarred Question",
}

# Months list for date formatting (1-indexed)
_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Meilisearch sort parameter map
_SORT_MAP: Dict[str, List[str]] = {
    "relevance": [],
    "chronological": ["date:asc", "sequence_within_sitting:asc"],
    "reverse_chronological": ["date:desc", "sequence_within_sitting:desc"],
}

# Markers that indicate the start of a supplementary exchange in Q+A text
_SUPPLEMENTARY_RE = re.compile(
    r"(SUPPLEMENTARY\s+QUESTION|SUP\.?\s*Q\.?|Supplementary\s+Q(?:uestion)?)",
    re.IGNORECASE,
)

# Token pattern for snippet term matching
_WORD_RE = re.compile(r"[a-zA-Z0-9/\.\-]+")


# ── Date display ──────────────────────────────────────────────────────────────

def format_date_display(date_val: Any) -> Optional[str]:
    """
    Convert a date value (string YYYY-MM-DD or datetime.date) to
    "DD Month YYYY" format.  Returns None for null / unparseable input.
    """
    if date_val is None:
        return None
    try:
        if isinstance(date_val, str):
            dt = datetime.strptime(date_val[:10], "%Y-%m-%d")
        else:
            # datetime.date or similar
            dt = datetime(date_val.year, date_val.month, date_val.day)
        return f"{dt.day} {_MONTHS[dt.month]} {dt.year}"
    except (ValueError, AttributeError, IndexError):
        return None


# ── Total display ─────────────────────────────────────────────────────────────

def format_total_display(total: int) -> str:
    """
    Return "10,000+" when total >= 10000; otherwise comma-formatted integer.
    """
    if total >= MAX_TOTAL_HITS:
        return "10,000+"
    return f"{total:,}"


# ── Proceeding type label ─────────────────────────────────────────────────────

def get_proceeding_type_label(proceeding_type: Optional[str]) -> Optional[str]:
    if proceeding_type is None:
        return None
    return _PROCEEDING_TYPE_LABELS.get(proceeding_type, proceeding_type.replace("_", " ").title())


# ── Snippet generation ────────────────────────────────────────────────────────

def _tokenize_query(query: str) -> List[str]:
    """Return lowercased tokens from *query*."""
    return _WORD_RE.findall(query.lower())


def _merge_expansion_terms(
    query_terms: List[str], expansion_notice: Optional[List[str]]
) -> List[str]:
    """Return query_terms extended with tokens from expansion_notice strings.

    Meilisearch expands synonyms at search time, so results may match on terms
    the user never typed.  Including those tokens in snippet highlighting makes
    the relevance signal visible to the user.
    """
    if not expansion_notice:
        return query_terms
    merged: set = set(query_terms)
    for term in expansion_notice:
        merged.update(_tokenize_query(term))
    return list(merged)


def _find_supplementary_offset(text: str) -> int:
    """
    Return the character offset where the first supplementary exchange begins,
    or -1 if the text has no supplementary section.
    """
    m = _SUPPLEMENTARY_RE.search(text)
    return m.start() if m else -1


def _build_snippet(
    text: str, query_terms: List[str], snippet_words: int = DEFAULT_SNIPPET_WORDS
) -> Tuple[Optional[str], bool]:
    """
    Extract the best *snippet_words*-word snippet from *text* for the given
    *query_terms*.  *snippet_words* is the effective snippet size resolved per
    request (F02/F05, PRD v3.3); shorter texts are returned in full (no padding).

    Steps:
      1. Split text into word-level tokens with their character offsets.
      2. Use a sliding *snippet_words* window to find the window with the
         highest density of query terms.
      3. HTML-escape the raw snippet text.
      4. Wrap each matched term with <mark>…</mark> tags.

    Returns:
        (snippet_html, snippet_from_supplementary)
        - snippet_html: None when text is empty/null.
        - snippet_from_supplementary: True when the best window starts at or
          after the first supplementary exchange marker.
    """
    if not text:
        return None, False

    # Word positions: list of (word, start_char, end_char) in original text
    word_positions: List[Tuple[str, int, int]] = [
        (m.group(), m.start(), m.end()) for m in _WORD_RE.finditer(text)
    ]
    if not word_positions:
        return None, False

    query_set = set(query_terms)
    window = min(snippet_words, len(word_positions))

    best_start = 0
    best_count = -1

    for i in range(len(word_positions) - window + 1):
        count = sum(
            1 for w, _, _ in word_positions[i : i + window]
            if w.lower() in query_set
        )
        if count > best_count:
            best_count = count
            best_start = i

    # Character span of the best window
    win_words = word_positions[best_start : best_start + window]
    char_start = win_words[0][1]
    char_end = win_words[-1][2]

    # Build the raw snippet string, preserving whitespace between words
    raw_snippet = text[char_start:char_end]

    # HTML-escape first, then re-apply <mark> wrapping
    escaped = html.escape(raw_snippet)

    # Rebuild the snippet with <mark> tags around query terms.
    # We work token-by-token to avoid double-escaping.
    def _mark_terms(s: str, terms: set) -> str:
        parts: List[str] = []
        prev_end = 0
        for m in _WORD_RE.finditer(s):
            if m.start() > prev_end:
                parts.append(s[prev_end : m.start()])
            word = m.group()
            if word.lower() in terms:
                parts.append(f"<mark>{word}</mark>")
            else:
                parts.append(word)
            prev_end = m.end()
        if prev_end < len(s):
            parts.append(s[prev_end:])
        return "".join(parts)

    snippet_html = _mark_terms(escaped, query_set)

    # Detect whether the best-match passage is from the supplementary section.
    # We check whether the FIRST MATCHED TERM in the window falls at or after
    # the supplementary marker, rather than the window's start character.
    # This handles the case where the entire short text fits in one window.
    sup_offset = _find_supplementary_offset(text)
    snippet_from_supplementary = False
    if sup_offset >= 0:
        for w, wstart, _ in win_words:
            if w.lower() in query_set:
                snippet_from_supplementary = wstart >= sup_offset
                break

    return snippet_html, snippet_from_supplementary


# ── Filter expression builder ─────────────────────────────────────────────────

def build_filter_expression(filters: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Construct a Meilisearch filter expression string from the *filters* dict.

    Active filter parts are joined with AND.
    Returns None when no filters are active.
    """
    if not filters:
        return None

    parts: List[str] = []

    # sources
    sources = filters.get("sources")
    if sources:
        quoted = ", ".join(f'"{s}"' for s in sources)
        parts.append(f"source IN [{quoted}]")

    # proceeding_types
    ptypes = filters.get("proceeding_types")
    if ptypes:
        quoted = ", ".join(f'"{p}"' for p in ptypes)
        parts.append(f"proceeding_type IN [{quoted}]")

    # date range
    date_from = filters.get("date_from")
    if date_from:
        parts.append(f'date >= "{date_from}"')

    date_to = filters.get("date_to")
    if date_to:
        parts.append(f'date <= "{date_to}"')

    # speaker substring
    speaker = filters.get("speaker")
    if speaker and speaker.strip():
        escaped = speaker.strip().replace('"', '\\"')
        parts.append(f'speaker_name CONTAINS "{escaped}"')

    # session substring
    session = filters.get("session")
    if session and session.strip():
        escaped = session.strip().replace('"', '\\"')
        parts.append(f'session_name CONTAINS "{escaped}"')

    # subject substring
    subject = filters.get("subject")
    if subject and subject.strip():
        escaped = subject.strip().replace('"', '\\"')
        parts.append(f'subject CONTAINS "{escaped}"')

    return " AND ".join(parts) if parts else None


# ── Sort parameter mapper ─────────────────────────────────────────────────────

def build_sort_params(sort: str) -> List[str]:
    """Return the Meilisearch sort parameter list for the given *sort* value."""
    return _SORT_MAP.get(sort, [])


# ── Debug helpers ─────────────────────────────────────────────────────────────

# snake_case SDK param → camelCase Meilisearch API param
_PARAM_CAMEL: Dict[str, str] = {
    "hits_per_page": "hitsPerPage",
    "page": "page",
    "filter": "filter",
    "sort": "sort",
    "attributes_to_crop": "attributesToCrop",
    "crop_length": "cropLength",
    "crop_marker": "cropMarker",
    "show_ranking_score": "showRankingScore",
    "show_ranking_score_details": "showRankingScoreDetails",
    "attributes_to_retrieve": "attributesToRetrieve",
}


def _build_debug_request_body(query: str, search_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Build the camelCase Meilisearch request body for the debug envelope."""
    body: Dict[str, Any] = {"q": query}
    for k, v in search_kwargs.items():
        body[_PARAM_CAMEL.get(k, k)] = v
    return body


def _meili_result_to_dict(raw: Any) -> Any:
    """Convert a SearchResults object to a JSON-serializable dict."""
    try:
        return raw.model_dump()
    except AttributeError:
        pass
    try:
        return raw.dict()
    except AttributeError:
        pass
    # Manual fallback using known attributes
    result: Dict[str, Any] = {}
    for attr, key in [
        ("hits", "hits"),
        ("total_hits", "totalHits"),
        ("total_pages", "totalPages"),
        ("page", "page"),
        ("hits_per_page", "hitsPerPage"),
        ("query", "query"),
        ("processing_time_ms", "processingTimeMs"),
    ]:
        val = getattr(raw, attr, None)
        if val is not None:
            result[key] = val
    return result


# ── Result formatter ──────────────────────────────────────────────────────────

def format_result(
    hit: Dict[str, Any],
    query_terms: List[str],
    debug: bool = False,
    snippet_words: int = DEFAULT_SNIPPET_WORDS,
) -> Dict[str, Any]:
    """
    Convert a raw Meilisearch hit dict into the API result shape.

    When debug=True, adds _rankingScore, _rankingScoreDetails (if present),
    and _meili_document (the full index document) for the ResultDebugPanel.
    """
    full_text = hit.get("full_text_en")
    date_val = hit.get("date")

    result: Dict[str, Any] = {
        "id": hit.get("id"),
        "record_type": hit.get("record_type"),
        "source": hit.get("source"),
        "proceeding_type": hit.get("proceeding_type"),
        "proceeding_type_label": get_proceeding_type_label(hit.get("proceeding_type")),
        "date": str(date_val) if date_val else None,
        "date_display": format_date_display(date_val),
        "session_name": hit.get("session_name"),
        "subject": hit.get("subject"),
        "is_translated": hit.get("is_translated", False),
        "lang_original": hit.get("lang_original"),
        "time_of_day": hit.get("time_of_day"),
        "source_url": hit.get("source_url"),
        # Speech fields
        "speaker_name": hit.get("speaker_name"),
        "speaker_party": hit.get("speaker_party"),
        "speaker_constituency_or_state": hit.get("speaker_constituency_or_state"),
        "speaker_name_unresolved": hit.get("speaker_name_unresolved", False),
        # Q+A fields
        "question_number": hit.get("question_number"),
        "questioner_names": hit.get("questioner_names"),
        "questioner_party": hit.get("questioner_party"),
        "minister_name": hit.get("minister_name"),
        "ministry": hit.get("ministry"),
    }

    # Only include snippet fields when full_text_en is present — null full_text_en
    # means no English text is available and the frontend handles display itself.
    # Omitting the keys entirely matches the documented API contract (DATA-MODELS.md 3.1).
    if full_text:
        snippet_html, snippet_from_sup = _build_snippet(full_text, query_terms, snippet_words)
        result["snippet"] = snippet_html
        result["snippet_from_supplementary"] = snippet_from_sup

    if debug:
        result["_rankingScore"] = hit.get("_rankingScore")
        if "_rankingScoreDetails" in hit:
            result["_rankingScoreDetails"] = hit["_rankingScoreDetails"]
        # Full index document for the "Document in index" debug section
        result["_meili_document"] = hit

    return result


# ── Main search entry point ───────────────────────────────────────────────────

async def execute_search(
    query: str,
    filters: Optional[Dict[str, Any]],
    sort: str,
    page: int,
    meili_client: Any,
    expansion_notice: Optional[List[str]] = None,
    debug: bool = False,
    snippet_size: Any = None,
) -> Dict[str, Any]:
    """
    Execute a search against the Meilisearch parliamentary_records index.

    Args:
        query:            Stop-word-stripped query string.
        filters:          Structured filters dict (sources, proceeding_types, etc.)
        sort:             Sort key: "relevance" | "chronological" | "reverse_chronological"
        page:             1-based page number.
        meili_client:     meilisearch.AsyncClient instance.
        expansion_notice: Pre-computed expansion notice list from query_expander.
        debug:            When True, adds score retrieval params + returns debug
                          envelope (F10, PRD v3.0).  Exempt from PERF-1 (PERF-3).
        snippet_size:     Optional raw `snippet_size` request value (F02/F05, PRD
                          v3.3).  Resolved to an effective snippet size (clamp
                          20–1000, else SNIPPET_DEFAULT_WORDS default 100) that
                          drives Meilisearch cropLength.  Never a validation error.

    Returns:
        API-shaped response dict.

    Raises:
        Exception: propagated from Meilisearch on backend errors.
    """
    filter_expr = build_filter_expression(filters)
    sort_params = build_sort_params(sort)
    effective_snippet_size = resolve_effective_snippet_size(snippet_size)

    index = meili_client.index(MEILI_INDEX_NAME)
    search_kwargs: Dict[str, Any] = {
        "hits_per_page": PER_PAGE,
        "page": page,
        # F02/F05 (PRD v3.3): dynamic snippet size. cropLength is the effective
        # snippet size resolved per request from `snippet_size` (clamp 20–1000)
        # or the operator default (SNIPPET_DEFAULT_WORDS, default 100).
        # Meilisearch crops full_text_en to a window of that many words centred
        # on the densest match passage; shorter texts are returned in full.
        "attributes_to_crop": ["full_text_en"],
        "crop_length": effective_snippet_size,
        "crop_marker": "…",
    }
    if filter_expr:
        search_kwargs["filter"] = filter_expr
    if sort_params:
        search_kwargs["sort"] = sort_params

    if debug:
        search_kwargs["show_ranking_score"] = True
        search_kwargs["show_ranking_score_details"] = True
        search_kwargs["attributes_to_retrieve"] = ["*"]

    raw = await index.search(query, **search_kwargs)

    hits = raw.hits or []
    total = raw.total_hits or 0
    total_pages = raw.total_pages or 1
    current_page = raw.page or page
    per_page = raw.hits_per_page or PER_PAGE

    query_terms = _tokenize_query(query)
    all_terms = _merge_expansion_terms(query_terms, expansion_notice)
    results = [
        format_result(hit, all_terms, debug=debug, snippet_words=effective_snippet_size)
        for hit in hits
    ]

    response: Dict[str, Any] = {
        "total": total,
        "total_display": format_total_display(total),
        "page": current_page,
        "total_pages": total_pages,
        "per_page": per_page,
        "expansion_notice": expansion_notice or [],
        "results": results,
    }

    if debug:
        meili_url = os.environ.get("MEILISEARCH_URL", "")
        search_url = f"{meili_url}/indexes/{MEILI_INDEX_NAME}/search"
        debug_body = _build_debug_request_body(query, search_kwargs)
        response["debug"] = {
            "processed_query": query,
            "meilisearch_request": {
                "method": "POST",
                "url": search_url,
                "body": debug_body,
            },
            "meilisearch_response": _meili_result_to_dict(raw),
        }

    return response
