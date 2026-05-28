"""
GET /api/status route — returns the most recent ingestion run summary from
the index_status PostgreSQL table.  Three possible response shapes:

  1. Populated  — a completed ingestion run exists.
  2. Never-run  — index_status table is empty (ingestion never ran).
  3. Unavailable — table is unreadable or malformed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends

from api.lib.db import get_pool

router = APIRouter()
logger = logging.getLogger(__name__)

_QUERY = "SELECT * FROM index_status ORDER BY run_completed_at DESC LIMIT 1"

# ── Response builders ─────────────────────────────────────────────────────────

def _source_block(count: int, date_from: Any, date_to: Any) -> dict:
    return {
        "count": count or 0,
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
    }


def _never_run_response() -> dict:
    return {
        "status": "ok",
        "total_records": 0,
        "sources": {
            "ca": _source_block(0, None, None),
            "ls": _source_block(0, None, None),
            "rs": _source_block(0, None, None),
        },
        "last_updated": None,
    }


def _populated_response(row: Any) -> dict:
    """
    Build the populated response from an asyncpg Record (or dict-like row).
    """
    def _get(key: str) -> Any:
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            return None

    run_at = _get("run_completed_at")
    last_updated = run_at.isoformat() if run_at else None

    return {
        "status": "ok",
        "total_records": _get("total_records") or 0,
        "sources": {
            "ca": _source_block(
                _get("ca_count"), _get("ca_date_from"), _get("ca_date_to")
            ),
            "ls": _source_block(
                _get("ls_count"), _get("ls_date_from"), _get("ls_date_to")
            ),
            "rs": _source_block(
                _get("rs_count"), _get("rs_date_from"), _get("rs_date_to")
            ),
        },
        "last_updated": last_updated,
    }


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def get_status(pool: Any = Depends(get_pool)) -> Any:
    """
    GET /api/status — return the most recent ingestion run summary.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(_QUERY)
    except Exception as exc:
        logger.warning("index_status query failed: %s", exc)
        return {"status": "unavailable"}

    if row is None:
        return _never_run_response()

    try:
        return _populated_response(row)
    except Exception as exc:
        logger.warning("index_status row malformed: %s", exc)
        return {"status": "unavailable"}
