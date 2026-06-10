"""
GET /api/status route — returns live document counts from the speeches and
qa_exchanges tables, grouped by source.  Three possible response shapes:

  1. Populated  — at least one indexed record exists.
  2. Never-run  — both tables are empty (ingestion never ran).
  3. Unavailable — tables are unreadable or malformed.

last_updated is taken from the most recent index_status run timestamp (when
present) and reflects when ingestion last completed, not the count query time.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from api.lib.db import get_pool

router = APIRouter()
logger = logging.getLogger(__name__)

# Live per-source counts and date ranges from the actual indexed tables.
_LIVE_COUNTS_QUERY = """
SELECT
    source,
    COUNT(*)    AS count,
    MIN(date)   AS date_from,
    MAX(date)   AS date_to
FROM (
    SELECT source, date FROM speeches
    UNION ALL
    SELECT source, date FROM qa_exchanges
) combined
GROUP BY source
"""

_LAST_UPDATED_QUERY = (
    "SELECT run_completed_at FROM index_status "
    "ORDER BY run_completed_at DESC LIMIT 1"
)

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


def _build_response(rows: list[Any], last_updated: Any) -> dict:
    by_source: dict[str, dict] = {}
    for row in rows:
        src = str(row["source"]).lower()
        by_source[src] = {
            "count": row["count"] or 0,
            "date_from": row["date_from"],
            "date_to": row["date_to"],
        }

    sources = {}
    total = 0
    for key in ("ca", "ls", "rs"):
        entry = by_source.get(key, {})
        count = entry.get("count", 0)
        total += count
        sources[key] = _source_block(count, entry.get("date_from"), entry.get("date_to"))

    last_updated_str = last_updated.isoformat() if last_updated else None

    return {
        "status": "ok",
        "total_records": total,
        "sources": sources,
        "last_updated": last_updated_str,
    }


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def get_status(pool: Any = Depends(get_pool)) -> Any:
    """
    GET /api/status — return live record counts from speeches + qa_exchanges.
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(_LIVE_COUNTS_QUERY)
            last_updated_row = await conn.fetchrow(_LAST_UPDATED_QUERY)
    except Exception as exc:
        logger.warning("status query failed: %s", exc)
        return {"status": "unavailable"}

    if not rows:
        return _never_run_response()

    try:
        last_updated = last_updated_row["run_completed_at"] if last_updated_row else None
        return _build_response(rows, last_updated)
    except Exception as exc:
        logger.warning("status response build failed: %s", exc)
        return {"status": "unavailable"}
