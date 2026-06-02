"""
Record service for SansadSearch.

Responsibilities:
- Fetch a single record by id from speeches UNION ALL qa_exchanges.
- Resolve adjacent neighbours (prev/next by sequence_within_sitting) in the same sitting.
- Compute sitting_total.
- Format the combined response per DATA-MODELS §3.3.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from api.services.search import format_date_display, get_proceeding_type_label

logger = logging.getLogger(__name__)

# ── SQL ───────────────────────────────────────────────────────────────────────

_RECORD_QUERY = """
SELECT
    id::text AS id,
    source,
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
FROM speeches
WHERE id = $1::uuid
UNION ALL
SELECT
    id::text AS id,
    source,
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
FROM qa_exchanges
WHERE id = $1::uuid
"""

# Returns all records in the same sitting ordered by sequence_within_sitting.
# IS NOT DISTINCT FROM handles NULL sitting_number (CA records) correctly.
_SITTING_QUERY = """
SELECT id::text AS id, sequence_within_sitting
FROM (
    SELECT id, sequence_within_sitting FROM speeches
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
    UNION ALL
    SELECT id, sequence_within_sitting FROM qa_exchanges
    WHERE source = $1
      AND date = $2
      AND sitting_number IS NOT DISTINCT FROM $3
) t
ORDER BY sequence_within_sitting
"""


# ── Service ───────────────────────────────────────────────────────────────────

async def fetch_record(conn: Any, record_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single record by id and return the formatted response dict,
    or None if the id does not exist in either table.

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

    # Fetch all records in the same sitting to compute total and neighbours.
    try:
        sitting_rows = await conn.fetch(
            _SITTING_QUERY,
            row["source"],
            row["date"],
            row["sitting_number"],
        )
    except Exception as exc:
        logger.warning("sitting query error: %s", exc)
        sitting_rows = []

    return _build_response(row, sitting_rows)


# ── Response builder ──────────────────────────────────────────────────────────

def _build_response(
    row: Any,
    sitting_rows: List[Any],
) -> Dict[str, Any]:
    current_seq = row["sequence_within_sitting"]
    sitting_total = len(sitting_rows)

    prev_id: Optional[str] = None
    next_id: Optional[str] = None
    if current_seq is not None:
        for sr in sitting_rows:
            seq = sr["sequence_within_sitting"]
            if seq == current_seq - 1:
                prev_id = sr["id"]
            elif seq == current_seq + 1:
                next_id = sr["id"]

    date_val = row["date"]
    date_str: Optional[str] = str(date_val) if date_val is not None else None

    questioner_names = row["questioner_names"]
    if questioner_names is not None:
        questioner_names = list(questioner_names)

    return {
        "id": row["id"],
        "record_type": row["record_type"],
        "source": row["source"],
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
        "sequence_within_sitting": current_seq,
        "sitting_total": sitting_total,
        "adjacent": {
            "prev_id": prev_id,
            "next_id": next_id,
        },
    }
