"""
Record service for SansadSearch.

Responsibilities:
- Fetch a single record by id from speeches UNION ALL qa_exchanges.
- Resolve same-sitting boundary flags (has_prev / has_next) and sitting_total
  for the F09 detail page (PRD v3.0 contract — replaces adjacent prev_id/next_id).
- Serve the F09 inline adjacent range-fetch (GET /api/record/{id}/adjacent):
  up to `limit` records strictly below/above a sequence position in the same
  sitting, always returned in ascending sequence order, with a has_more flag.
- Format the combined response per DATA-MODELS §3.3 and §3.4.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api.services.search import format_date_display, get_proceeding_type_label

logger = logging.getLogger(__name__)

# ── Column projections ────────────────────────────────────────────────────────
# Shared SELECT column lists so the single-record query and the adjacent
# range-fetch query return identical record shapes. The two tables are
# projected to a common column set (speech-only fields NULL on Q+A rows and
# vice versa) so they can be UNION ALL-ed.

_SPEECH_COLUMNS = """
    id::text AS id,
    source,
    lok_sabha_number,
    proceeding_type,
    date,
    session_name,
    session_number,
    sitting_number,
    subject,
    full_text_en,
    lang_original,
    time_of_day,
    word_count,
    is_translated,
    has_untranslated_content,
    page_reference,
    source_url,
    sequence_within_sitting,
    volume,
    speaker_name,
    speaker_role,
    speaker_party,
    speaker_constituency_or_state,
    speaker_name_unresolved,
    NULL::integer AS question_number,
    NULL::text[] AS questioner_names,
    NULL::varchar AS questioner_party,
    NULL::varchar AS minister_name,
    NULL::varchar AS ministry,
    'speech'::text AS record_type
"""

_QA_COLUMNS = """
    id::text AS id,
    source,
    lok_sabha_number,
    proceeding_type,
    date,
    session_name,
    session_number,
    sitting_number,
    subject,
    full_text_en,
    lang_original,
    time_of_day,
    word_count,
    is_translated,
    has_untranslated_content,
    page_reference,
    source_url,
    sequence_within_sitting,
    NULL::integer AS volume,
    NULL::varchar AS speaker_name,
    NULL::varchar AS speaker_role,
    NULL::varchar AS speaker_party,
    NULL::varchar AS speaker_constituency_or_state,
    NULL::boolean AS speaker_name_unresolved,
    question_number,
    questioner_names,
    questioner_party,
    minister_name,
    ministry,
    'qa'::text AS record_type
"""

# ── SQL ───────────────────────────────────────────────────────────────────────

_RECORD_QUERY = f"""
SELECT {_SPEECH_COLUMNS}
FROM speeches
WHERE id = $1::uuid
UNION ALL
SELECT {_QA_COLUMNS}
FROM qa_exchanges
WHERE id = $1::uuid
"""

# Returns the sequence number of every record in the same sitting (both tables).
# IS NOT DISTINCT FROM handles NULL sitting_number (CA records) correctly.
_SITTING_SEQ_QUERY = """
SELECT sequence_within_sitting
FROM (
    SELECT sequence_within_sitting FROM speeches
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
    UNION ALL
    SELECT sequence_within_sitting FROM qa_exchanges
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
) t
"""

# Resolves the focal record's sitting identity (and its own sequence) by id.
_FOCAL_SITTING_QUERY = """
SELECT source, date, sitting_number, sequence_within_sitting
FROM (
    SELECT source, date, sitting_number, sequence_within_sitting FROM speeches
    WHERE id = $1::uuid
    UNION ALL
    SELECT source, date, sitting_number, sequence_within_sitting FROM qa_exchanges
    WHERE id = $1::uuid
) t
"""


def _adjacent_batch_query(direction: str) -> str:
    """
    Build the same-sitting range-fetch query for a direction.

    `prev`: records with sequence_within_sitting < from_seq, ordered DESC
            (closest to focal first).
    `next`: records with sequence_within_sitting > from_seq, ordered ASC.

    `op` and `order` are internal constants chosen from a fixed set — never
    user input — so f-string interpolation here is safe. All values are
    parameterised.
    """
    op = "<" if direction == "prev" else ">"
    order = "DESC" if direction == "prev" else "ASC"
    return f"""
SELECT * FROM (
    SELECT {_SPEECH_COLUMNS}
    FROM speeches
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
      AND sequence_within_sitting {op} $4
    UNION ALL
    SELECT {_QA_COLUMNS}
    FROM qa_exchanges
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
      AND sequence_within_sitting {op} $4
) t
ORDER BY sequence_within_sitting {order}
LIMIT $5
"""


# ── Service ───────────────────────────────────────────────────────────────────

async def fetch_record(conn: Any, record_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single record by id and return the formatted response dict
    (DATA-MODELS §3.3), or None if the id does not exist in either table.

    Catches all DB exceptions (including invalid UUID cast errors) and returns
    None so the caller renders a 404.
    """
    try:
        row = await conn.fetchrow(_RECORD_QUERY, record_id)
    except Exception as exc:
        logger.debug("record fetchrow error for id=%s: %s", record_id, exc)
        return None

    if row is None:
        return None

    # Fetch sequence numbers of all records in the same sitting to compute the
    # total and the boundary flags.
    try:
        sitting_rows = await conn.fetch(
            _SITTING_SEQ_QUERY,
            row["source"],
            row["date"],
            row["sitting_number"],
        )
    except Exception as exc:
        logger.warning("sitting query error: %s", exc)
        sitting_rows = []

    return _build_response(row, sitting_rows)


async def fetch_adjacent(
    conn: Any,
    record_id: str,
    direction: str,
    from_seq: int,
    limit: int = 5,
) -> Optional[Dict[str, Any]]:
    """
    F09 inline adjacent loading (DATA-MODELS §3.4).

    Resolve the focal record's sitting, then return up to `limit` records
    strictly below (`prev`) or above (`next`) `from_seq`, always in ascending
    sequence order, plus a `has_more` flag.

    Returns None if the focal `record_id` does not exist (caller → 404).
    """
    limit = max(1, min(limit, 5))

    try:
        focal = await conn.fetchrow(_FOCAL_SITTING_QUERY, record_id)
    except Exception as exc:
        logger.debug("adjacent focal fetch error for id=%s: %s", record_id, exc)
        return None

    if focal is None:
        return None

    query = _adjacent_batch_query(direction)
    try:
        # Fetch one extra row to detect whether more records remain beyond
        # the returned batch (has_more).
        rows = await conn.fetch(
            query,
            focal["source"],
            focal["date"],
            focal["sitting_number"],
            from_seq,
            limit + 1,
        )
    except Exception as exc:
        logger.warning("adjacent batch query error: %s", exc)
        rows = []

    rows = list(rows)
    has_more = len(rows) > limit
    rows = rows[:limit]

    # Rows come back closest-to-focal first. For `prev` that is DESC order;
    # reverse to ascending so the client renders them top-to-bottom in
    # document order. `next` is already ascending.
    if direction == "prev":
        rows = list(reversed(rows))

    records = [_format_record_fields(r) for r in rows]

    return {
        "direction": direction,
        "records": records,
        "has_more": has_more,
    }


# ── Response builders ─────────────────────────────────────────────────────────

def _format_record_fields(row: Any) -> Dict[str, Any]:
    """
    Format a record row into the common field dict shared by the detail
    response (§3.3) and each adjacent record (§3.4). Excludes the
    sitting-context fields (sitting_total, has_prev, has_next).
    """
    date_val = row["date"]
    date_str: Optional[str] = str(date_val) if date_val is not None else None

    questioner_names = row["questioner_names"]
    if questioner_names is not None:
        questioner_names = list(questioner_names)

    return {
        "id": row["id"],
        "record_type": row["record_type"],
        "source": row["source"],
        "lok_sabha_number": row["lok_sabha_number"],
        "proceeding_type": row["proceeding_type"],
        "proceeding_type_label": get_proceeding_type_label(row["proceeding_type"]),
        "date": date_str,
        "date_display": format_date_display(date_val),
        "time_of_day": row["time_of_day"],
        "session_name": row["session_name"],
        "session_number": row["session_number"],
        "sitting_number": row["sitting_number"],
        "volume": row["volume"],
        "subject": row["subject"],
        "full_text_en": row["full_text_en"],
        "lang_original": row["lang_original"],
        "is_translated": row["is_translated"],
        "has_untranslated_content": row["has_untranslated_content"],
        "page_reference": row["page_reference"],
        "word_count": row["word_count"],
        "source_url": row["source_url"],
        "speaker_name": row["speaker_name"],
        "speaker_role": row["speaker_role"],
        "speaker_party": row["speaker_party"],
        "speaker_constituency_or_state": row["speaker_constituency_or_state"],
        "speaker_name_unresolved": row["speaker_name_unresolved"],
        "question_number": row["question_number"],
        "questioner_names": questioner_names,
        "questioner_party": row["questioner_party"],
        "minister_name": row["minister_name"],
        "ministry": row["ministry"],
        "sequence_within_sitting": row["sequence_within_sitting"],
    }


def _build_response(row: Any, sitting_rows: List[Any]) -> Dict[str, Any]:
    """
    Build the §3.3 detail response: common record fields plus sitting context
    (sitting_total, has_prev, has_next).
    """
    current_seq = row["sequence_within_sitting"]
    sitting_total = len(sitting_rows)

    has_prev = False
    has_next = False
    if current_seq is not None:
        for sr in sitting_rows:
            seq = sr["sequence_within_sitting"]
            if seq is None:
                continue
            if seq < current_seq:
                has_prev = True
            elif seq > current_seq:
                has_next = True

    response = _format_record_fields(row)
    response["sitting_total"] = sitting_total
    response["has_prev"] = has_prev
    response["has_next"] = has_next
    return response
