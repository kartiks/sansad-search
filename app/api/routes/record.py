"""
GET /api/record/{record_id} — fetch a single record by id from PostgreSQL.

Returns the full record with adjacent navigation and sitting total.
Returns 404 when no row in either speeches or qa_exchanges matches the id.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.lib.db import get_pool
from api.services.record import fetch_record

router = APIRouter()
logger = logging.getLogger(__name__)

_NOT_FOUND = {"error": "not_found", "message": "Record not found."}


@router.get("/api/record/{record_id}")
async def get_record_detail(
    record_id: str,
    pool: Any = Depends(get_pool),
) -> Any:
    """
    GET /api/record/{record_id}

    Served from PostgreSQL (not Meilisearch). Returns full record fields plus
    adjacent prev/next ids and sitting_total. 404 when id not found.
    """
    async with pool.acquire() as conn:
        record = await fetch_record(conn, record_id)

    if record is None:
        return JSONResponse(status_code=404, content=_NOT_FOUND)

    return record
