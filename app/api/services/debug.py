"""
Debug service for F10 (PRD v3.0).

Serves two lazy-fetch endpoints:
  - GET /api/debug/processed/{id}  — full speeches/qa_exchanges row
  - GET /api/debug/raw/{id}        — full raw_documents row resolved via
                                     canonical_doc_id + source
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Serialisation ─────────────────────────────────────────────────────────────

def _serialize_value(val: Any) -> Any:
    """Convert asyncpg-returned values to JSON-safe Python types."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime.datetime):
        return val.isoformat()
    if isinstance(val, datetime.date):
        return val.isoformat()
    if isinstance(val, list):
        return [_serialize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    return val


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert an asyncpg Record to a JSON-safe dict (all columns)."""
    return {k: _serialize_value(v) for k, v in dict(row).items()}


# ── Service ───────────────────────────────────────────────────────────────────

async def fetch_processed_record(conn: Any, record_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the full speeches or qa_exchanges row for the given id.

    Returns {"table": "speeches"|"qa_exchanges", "row": {...}} or None (→ 404).
    Catches UUID cast errors and returns None so the caller renders a 404.
    """
    try:
        row = await conn.fetchrow(
            "SELECT * FROM speeches WHERE id = $1::uuid", record_id
        )
    except Exception as exc:
        logger.debug("debug processed fetchrow (speeches) error id=%s: %s", record_id, exc)
        return None

    if row is not None:
        return {"table": "speeches", "row": _row_to_dict(row)}

    try:
        row = await conn.fetchrow(
            "SELECT * FROM qa_exchanges WHERE id = $1::uuid", record_id
        )
    except Exception as exc:
        logger.debug("debug processed fetchrow (qa_exchanges) error id=%s: %s", record_id, exc)
        return None

    if row is not None:
        return {"table": "qa_exchanges", "row": _row_to_dict(row)}

    return None


async def fetch_raw_document(conn: Any, record_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the raw_documents row for the given processed record id.

    Resolution:
      1. Look up canonical_doc_id + source from speeches, then qa_exchanges.
      2. Fetch raw_documents WHERE canonical_doc_id=$1 AND corpus=$2.

    Returns {"row": {...}} or None (→ 404) when:
      - no processed record exists for this id
      - canonical_doc_id is NULL
      - no matching raw_documents row exists
    """
    canonical_doc_id: Optional[str] = None
    source: Optional[str] = None

    for table in ("speeches", "qa_exchanges"):
        try:
            proc = await conn.fetchrow(
                f"SELECT canonical_doc_id, source FROM {table} WHERE id = $1::uuid",  # noqa: S608 — table is an internal constant, not user input
                record_id,
            )
        except Exception as exc:
            logger.debug("debug raw lookup (%s) error id=%s: %s", table, record_id, exc)
            return None
        if proc is not None:
            canonical_doc_id = proc["canonical_doc_id"]
            source = proc["source"]
            break

    if not canonical_doc_id or not source:
        # Processed record not found, or canonical_doc_id is NULL
        return None

    try:
        raw = await conn.fetchrow(
            "SELECT * FROM raw_documents WHERE canonical_doc_id = $1 AND corpus = $2",
            canonical_doc_id,
            source,
        )
    except Exception as exc:
        logger.debug(
            "debug raw fetch error canonical_doc_id=%s corpus=%s: %s",
            canonical_doc_id, source, exc,
        )
        return None

    if raw is None:
        return None

    return {"row": _row_to_dict(raw)}
