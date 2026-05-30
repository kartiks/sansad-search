"""
Ingestion indexer: writes canonical records to PostgreSQL and pushes
denormalized documents to Meilisearch.

Public interface:
  build_dedup_key(record)          → compound dedup key string
  build_meili_document(record)     → Meilisearch document dict (fields excluded per spec)
  Indexer                          → main class; wraps pg_conn and meili_client

Indexer.index_record(record, checkpoint)
  → checks checkpoint store for duplicate, inserts into PG, enqueues for Meili push

Indexer.flush()
  → pushes buffered Meilisearch documents in one batch

Indexer.update_index_status()
  → writes one row to the index_status PostgreSQL table

Indexer.reindex_from_db()
  → reads all records from PostgreSQL and pushes to Meilisearch (no re-scraping)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from ingest.canonical.names import normalize_for_dedup
from ingest.checkpoints.store import CheckpointStore

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MEILI_INDEX_NAME = "parliamentary_records"
MEILI_BATCH_SIZE = 100

# Fields stored in PostgreSQL only; excluded from Meilisearch documents
_MEILI_EXCLUDED = frozenset({
    "page_reference",
    "has_untranslated_content",
    "session_number",
    "created_at",
    "dedup_key",
})

# All speeches-table columns (in INSERT order)
_SPEECH_COLUMNS = (
    "source", "proceeding_type", "date", "session_name", "session_number",
    "sitting_number", "subject", "speaker_name", "speaker_party",
    "speaker_constituency_or_state", "speaker_role", "sequence_within_sitting",
    "full_text_en", "is_translated", "has_untranslated_content",
    "speaker_name_unresolved", "source_url", "page_reference", "volume",
    "dedup_key",
)

# All qa_exchanges-table columns (in INSERT order)
_QA_COLUMNS = (
    "source", "proceeding_type", "date", "session_name", "session_number",
    "sitting_number", "question_number", "subject", "questioner_names",
    "questioner_party", "minister_name", "ministry",
    "full_text_en", "is_translated", "has_untranslated_content",
    "source_url", "page_reference", "dedup_key",
)


# ── Dedup key construction ─────────────────────────────────────────────────────

def build_dedup_key(record: dict[str, Any]) -> str:
    """
    Build the compound dedup key for a canonical record.

    Speech:   {source}_{date}_{sitting_number}_{proceeding_type}_{speaker_name_normalized}_{sequence}
    Q+A:      {source}_{date}_{sitting_number}_{proceeding_type}_{question_number}
    """
    record_type = record.get("record_type", "speech")
    source = record.get("source", "")
    date_val = record.get("date") or ""
    sitting = record.get("sitting_number") or 0
    pt = record.get("proceeding_type", "")

    if record_type == "qa":
        qnum = record.get("question_number") or 0
        return f"{source}_{date_val}_{sitting}_{pt}_{qnum}"

    # Speech
    speaker_norm = normalize_for_dedup(record.get("speaker_name"))
    seq = record.get("sequence_within_sitting") or 0
    return f"{source}_{date_val}_{sitting}_{pt}_{speaker_norm}_{seq}"


# ── Meilisearch document construction ─────────────────────────────────────────

def build_meili_document(record: dict[str, Any]) -> dict[str, Any]:
    """
    Build a Meilisearch document dict from a canonical record.

    - Includes record_type field
    - Excludes fields in _MEILI_EXCLUDED
    - Omits fields that are None or not applicable to the record type
      (no null-padding for missing fields)
    """
    doc: dict[str, Any] = {}
    for k, v in record.items():
        if k in _MEILI_EXCLUDED:
            continue
        if v is None:
            continue
        doc[k] = v
    return doc


# ── Indexer class ──────────────────────────────────────────────────────────────

class Indexer:
    """
    Writes canonical records to PostgreSQL and pushes to Meilisearch.

    Args:
        pg_conn:      psycopg2 connection (synchronous)
        meili_client: meilisearch.Client instance (synchronous)
    """

    def __init__(self, pg_conn: Any, meili_client: Any) -> None:
        self._pg = pg_conn
        self._meili = meili_client
        self._meili_batch: list[dict] = []

        # Counters for index_status
        self.counts: dict[str, int] = {"CA": 0, "LS": 0, "RS": 0}
        self.date_ranges: dict[str, list[str]] = {"CA": [], "LS": [], "RS": []}

    # ── Core indexing ──────────────────────────────────────────────────────────

    def index_record(
        self,
        record: dict[str, Any],
        checkpoint: CheckpointStore,
    ) -> bool:
        """
        Index one canonical record.

        Returns True if indexed, False if skipped (duplicate or missing date).
        The Meilisearch push is deferred — call flush() to send the batch.
        """
        # Date is required
        if not record.get("date"):
            logger.error(
                "Record missing date (source=%s, url=%s); skipping",
                record.get("source"), record.get("source_url"),
            )
            return False

        dedup_key = build_dedup_key(record)

        # Check in-memory checkpoint store first (fast path)
        if checkpoint.has_dedup_key(dedup_key):
            logger.debug("Duplicate dedup key %s; skipping", dedup_key)
            return False

        # Write to PostgreSQL
        record_with_key = dict(record, dedup_key=dedup_key)
        try:
            inserted = self._insert_record(record_with_key)
        except Exception as exc:
            # UniqueViolation or other constraint errors: treat as duplicate
            logger.warning(
                "PG insert failed for dedup_key=%s: %s; skipping", dedup_key, exc
            )
            return False

        if not inserted:
            return False

        # Record dedup key in checkpoint store
        checkpoint.add_dedup_key(dedup_key)

        # Track counts and date ranges for index_status
        source = record.get("source", "")
        if source in self.counts:
            self.counts[source] += 1
            date_val = record.get("date")
            if date_val:
                self.date_ranges[source].append(str(date_val))

        # Enqueue Meilisearch document
        doc = build_meili_document(record_with_key)
        if "id" in record:
            doc["id"] = record["id"]
        self._meili_batch.append(doc)

        if len(self._meili_batch) >= MEILI_BATCH_SIZE:
            self.flush()

        return True

    def _insert_record(self, record: dict[str, Any]) -> bool:
        """Insert record into the correct PostgreSQL table. Returns True on success."""
        record_type = record.get("record_type", "speech")
        cursor = self._pg.cursor()

        if record_type == "qa":
            return self._insert_qa(cursor, record)
        return self._insert_speech(cursor, record)

    def _insert_speech(self, cursor: Any, record: dict[str, Any]) -> bool:
        cols = _SPEECH_COLUMNS
        values = tuple(record.get(c) for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        cursor.execute(
            f"INSERT INTO speeches ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT (dedup_key) DO NOTHING "
            f"RETURNING id",
            values,
        )
        row = cursor.fetchone()
        self._pg.commit()
        if row:
            record["id"] = str(row[0])
            return True
        logger.debug("Speech with dedup_key=%s already exists", record.get("dedup_key"))
        return False

    def _insert_qa(self, cursor: Any, record: dict[str, Any]) -> bool:
        cols = _QA_COLUMNS
        values = tuple(record.get(c) for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        cursor.execute(
            f"INSERT INTO qa_exchanges ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT (dedup_key) DO NOTHING "
            f"RETURNING id",
            values,
        )
        row = cursor.fetchone()
        self._pg.commit()
        if row:
            record["id"] = str(row[0])
            return True
        logger.debug("Q+A with dedup_key=%s already exists", record.get("dedup_key"))
        return False

    # ── Meilisearch flush ─────────────────────────────────────────────────────

    def flush(self) -> int:
        """Push buffered documents to Meilisearch. Returns number of documents pushed."""
        if not self._meili_batch:
            return 0
        batch = list(self._meili_batch)
        self._meili_batch.clear()
        try:
            index = self._meili.index(MEILI_INDEX_NAME)
            index.add_documents(batch)
            logger.debug("Pushed %d documents to Meilisearch", len(batch))
        except Exception as exc:
            logger.error("Meilisearch push failed: %s", exc)
        return len(batch)

    # ── index_status update ───────────────────────────────────────────────────

    def update_index_status(self) -> None:
        """Write one row to the index_status PostgreSQL table."""
        cursor = self._pg.cursor()

        def _min_date(dates: list[str]) -> Optional[str]:
            return min(dates) if dates else None

        def _max_date(dates: list[str]) -> Optional[str]:
            return max(dates) if dates else None

        ca_dates = self.date_ranges.get("CA", [])
        ls_dates = self.date_ranges.get("LS", [])
        rs_dates = self.date_ranges.get("RS", [])

        cursor.execute(
            """
            INSERT INTO index_status (
                run_completed_at,
                total_records,
                ca_count, ca_date_from, ca_date_to,
                ls_count, ls_date_from, ls_date_to,
                rs_count, rs_date_from, rs_date_to
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                datetime.now(timezone.utc),
                sum(self.counts.values()),
                self.counts.get("CA", 0), _min_date(ca_dates), _max_date(ca_dates),
                self.counts.get("LS", 0), _min_date(ls_dates), _max_date(ls_dates),
                self.counts.get("RS", 0), _min_date(rs_dates), _max_date(rs_dates),
            ),
        )
        self._pg.commit()
        logger.info(
            "index_status updated: total=%d CA=%d LS=%d RS=%d",
            sum(self.counts.values()),
            self.counts.get("CA", 0),
            self.counts.get("LS", 0),
            self.counts.get("RS", 0),
        )

    # ── Re-index from PostgreSQL ───────────────────────────────────────────────

    def reindex_from_db(self) -> int:
        """
        Re-push all records from PostgreSQL to Meilisearch without re-scraping.

        Returns total number of documents pushed.
        """
        cursor = self._pg.cursor()
        total = 0

        for table, record_type in (("speeches", "speech"), ("qa_exchanges", "qa")):
            cursor.execute(f"SELECT * FROM {table}")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            for row in rows:
                record = dict(zip(columns, row))
                record["record_type"] = record_type
                doc = build_meili_document(record)
                if "id" in record:
                    doc["id"] = str(record["id"])
                self._meili_batch.append(doc)
                if len(self._meili_batch) >= MEILI_BATCH_SIZE:
                    total += self.flush()

        total += self.flush()
        logger.info("reindex_from_db: pushed %d documents to Meilisearch", total)
        return total
