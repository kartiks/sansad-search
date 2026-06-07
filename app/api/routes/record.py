"""
Record detail endpoints (F09), served from PostgreSQL.

- GET /api/record/{record_id}          — single record + sitting context
                                          (has_prev / has_next, sitting_total).
- GET /api/record/{record_id}/adjacent — inline adjacent range-fetch
                                          (direction, from_seq, limit).

Both return 404 when the focal id is not found in either table.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.lib.db import get_pool
from api.services.record import fetch_adjacent, fetch_record

router = APIRouter()
logger = logging.getLogger(__name__)

_NOT_FOUND = {"error": "not_found", "message": "Record not found."}


@router.get("/api/record/{record_id}/adjacent")
async def get_record_adjacent(
    record_id: str,
    direction: str = Query(...),
    from_seq: str = Query(...),
    limit: int = Query(5),
    pool: Any = Depends(get_pool),
) -> Any:
    """
    GET /api/record/{record_id}/adjacent

    Returns up to `limit` (default 5, max 5) same-sitting records strictly
    below (`prev`) or above (`next`) `from_seq`, always in ascending sequence
    order, plus `has_more`. Served from PostgreSQL.

    400 when `direction` is not prev/next or `from_seq` is not an integer.
    404 when the focal `record_id` does not exist (sitting cannot be resolved).
    """
    if direction not in ("prev", "next"):
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "message": "direction must be 'prev' or 'next'.",
            },
        )

    try:
        from_seq_int = int(from_seq)
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "message": "from_seq must be an integer.",
            },
        )

    async with pool.acquire() as conn:
        result = await fetch_adjacent(conn, record_id, direction, from_seq_int, limit)

    if result is None:
        return JSONResponse(status_code=404, content=_NOT_FOUND)

    return result


@router.get("/api/record/{record_id}")
async def get_record_detail(
    record_id: str,
    pool: Any = Depends(get_pool),
) -> Any:
    """
    GET /api/record/{record_id}

    Served from PostgreSQL (not Meilisearch). Returns full record fields plus
    sitting context (has_prev, has_next, sitting_total). 404 when id not found.
    """
    async with pool.acquire() as conn:
        record = await fetch_record(conn, record_id)

    if record is None:
        return JSONResponse(status_code=404, content=_NOT_FOUND)

    return record
