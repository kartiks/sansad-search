"""
POST /api/search route — full-text search across parliamentary records.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
from pydantic import BaseModel, field_validator

from api.lib.meilisearch_client import get_client
from api.services.query_expander import expand_query, strip_stop_words
from api.services.search import execute_search

router = APIRouter()

# Maximum query length (server truncates silently)
_MAX_QUERY_LEN = 500

# Minimum meaningful query length (non-whitespace characters)
_MIN_QUERY_CHARS = 2

# Valid source values
_VALID_SOURCES = frozenset({"CA", "LS", "RS"})

# Valid proceeding type values
_VALID_PROCEEDING_TYPES = frozenset({
    "debate", "zero_hour", "short_duration_discussion", "calling_attention",
    "adjournment_motion", "private_member_bill", "short_notice_question",
    "starred_question", "unstarred_question",
})

# Valid sort values
_VALID_SORTS = frozenset({"relevance", "chronological", "reverse_chronological"})

# Pattern for YYYY-MM-DD dates
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Non-alphanumeric-only query pattern (special chars only)
_MEANINGFUL_CHAR_RE = re.compile(r"[a-zA-Z0-9]")


# ── Pydantic request models ───────────────────────────────────────────────────

class FilterInput(BaseModel):
    sources: Optional[List[str]] = None
    proceeding_types: Optional[List[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    speaker: Optional[str] = None
    session: Optional[str] = None
    subject: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    filters: Optional[FilterInput] = None
    sort: str = "relevance"
    page: int = 1

    @field_validator("sort")
    @classmethod
    def sort_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_SORTS:
            raise ValueError(f"sort must be one of: {sorted(_VALID_SORTS)}")
        return v

    @field_validator("page")
    @classmethod
    def page_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page must be >= 1")
        return v


# ── Validation helpers ────────────────────────────────────────────────────────

def _validation_error_response(code: str, message: str) -> Dict[str, Any]:
    return {"error": "validation_error", "code": code, "message": message}


def _validate_request(
    query: str, filters: Optional[FilterInput]
) -> Optional[Dict[str, Any]]:
    """
    Validate the search request.  Returns an error dict on failure, else None.
    """
    # --- query must have at least 2 meaningful characters ---
    if not _MEANINGFUL_CHAR_RE.search(query):
        return _validation_error_response(
            "query_too_short",
            "Query must contain at least 2 characters.",
        )
    meaningful_chars = re.findall(r"[a-zA-Z0-9]", query)
    if len(meaningful_chars) < _MIN_QUERY_CHARS:
        return _validation_error_response(
            "query_too_short",
            "Query must contain at least 2 characters.",
        )

    # --- stop-words-only check ---
    _, only_stopwords = strip_stop_words(query)
    if only_stopwords:
        return _validation_error_response(
            "query_only_stopwords",
            "Your query contains only common words. Please add a more specific term.",
        )

    if filters is None:
        return None

    # --- sources ---
    if filters.sources is not None and len(filters.sources) == 0:
        return _validation_error_response(
            "sources_empty",
            "Select at least one legislative body.",
        )

    # --- proceeding_types ---
    if filters.proceeding_types is not None and len(filters.proceeding_types) == 0:
        return _validation_error_response(
            "proceeding_types_empty",
            "Select at least one proceeding type.",
        )

    # --- date range ordering ---
    df = filters.date_from
    dt = filters.date_to
    if df and dt:
        if _DATE_RE.match(df) and _DATE_RE.match(dt):
            if df > dt:
                return _validation_error_response(
                    "date_range_invalid",
                    "From date must be on or before To date.",
                )

    return None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/api/search")
async def search(
    body: SearchRequest,
    meili_client: Any = Depends(get_client),
    debug: Optional[str] = Query(default=None),
) -> Any:
    """
    POST /api/search — execute a full-text search and return paginated results.

    ?debug=1 (or ?debug=true) activates F10 debug mode: adds ranking score
    retrieval to the Meilisearch query and returns a top-level debug envelope.
    """
    # 1. Truncate query to 500 characters (silent)
    raw_query = body.query[:_MAX_QUERY_LEN]

    # 2. Validate
    filters = body.filters
    error = _validate_request(raw_query, filters)
    if error:
        return JSONResponse(status_code=400, content=error)

    # 3. Expand query (generates clean_query + expansion_notice)
    try:
        clean_query, expansion_notice = expand_query(raw_query)
    except Exception:
        clean_query = raw_query
        expansion_notice = []

    # 4. Build filter dict for the service layer
    filter_dict: Optional[Dict[str, Any]] = None
    if filters is not None:
        filter_dict = {}
        if filters.sources is not None:
            filter_dict["sources"] = filters.sources
        if filters.proceeding_types is not None:
            filter_dict["proceeding_types"] = filters.proceeding_types
        if filters.date_from:
            filter_dict["date_from"] = filters.date_from
        if filters.date_to:
            filter_dict["date_to"] = filters.date_to
        if filters.speaker and filters.speaker.strip():
            filter_dict["speaker"] = filters.speaker.strip()
        if filters.session and filters.session.strip():
            filter_dict["session"] = filters.session.strip()
        if filters.subject and filters.subject.strip():
            filter_dict["subject"] = filters.subject.strip()

    # 5. Execute search
    debug_active = debug in ("1", "true", "True")
    try:
        result = await execute_search(
            query=clean_query,
            filters=filter_dict,
            sort=body.sort,
            page=body.page,
            meili_client=meili_client,
            expansion_notice=expansion_notice,
            debug=debug_active,
        )
    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "search_unavailable",
                "message": "Search is temporarily unavailable.",
            },
        )

    return result
