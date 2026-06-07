"""
F10 debug endpoints (PRD v3.0).

- GET /api/debug/processed/{id}  — full speeches/qa_exchanges row
- GET /api/debug/raw/{id}        — full raw_documents row resolved via
                                   canonical_doc_id + source

No authentication (NFR SEC-1 — deliberate v1 choice, debug-only).
Both endpoints are exempt from PERF-1/PERF-2 (NFR PERF-3).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.lib.db import get_pool
from api.services.debug import fetch_processed_record, fetch_raw_document

router = APIRouter()
logger = logging.getLogger(__name__)

_NOT_FOUND_RECORD = {"error": "not_found", "message": "Record not found."}
_NOT_FOUND_RAW = {"error": "not_found", "message": "Raw document not available."}


@router.get("/api/debug/processed/{record_id}")
async def get_debug_processed(
    record_id: str,
    pool: Any = Depends(get_pool),
) -> Any:
    """
    GET /api/debug/processed/{id}

    Returns {"table": "speeches"|"qa_exchanges", "row": {...}} with every
    column including segments (JSONB) and canonical_doc_id. 404 when the
    id is not found in either table.
    """
    async with pool.acquire() as conn:
        result = await fetch_processed_record(conn, record_id)

    if result is None:
        return JSONResponse(status_code=404, content=_NOT_FOUND_RECORD)

    return result


@router.get("/api/debug/raw/{record_id}")
async def get_debug_raw(
    record_id: str,
    pool: Any = Depends(get_pool),
) -> Any:
    """
    GET /api/debug/raw/{id}

    Returns {"row": {...}} with the full raw_documents row resolved via the
    processed record's canonical_doc_id + source. 404 when no processed
    record exists, canonical_doc_id is NULL, or no matching raw row exists.
    """
    async with pool.acquire() as conn:
        result = await fetch_raw_document(conn, record_id)

    if result is None:
        return JSONResponse(status_code=404, content=_NOT_FOUND_RAW)

    return result
