"""
Ingestion indexer: writes canonical records to PostgreSQL and pushes
denormalized documents to Meilisearch.

Public interface:
  build_dedup_key(record)          → compound dedup key string
  build_meili_document(record)     → Meilisearch document dict (fields excluded per spec)
  Indexer                          → main class; wraps pg_conn and meili_client

Indexer.index_document(records, checkpoint, corpus=…, canonical_doc_id=…)
  → writes all of one document's records, their dedup keys and its
    processed_documents row in a single statement, then enqueues the Meili push

Indexer.index_record(record, checkpoint)
  → single-record insert (used as the fallback when a batch insert fails)

Indexer.next_sequence(source, date, sitting_number)
  → next free sequence_within_sitting for a sitting, from what is stored

Indexer.flush()
  → pushes buffered Meilisearch documents in one batch

Indexer.update_index_status()
  → writes one row to the index_status PostgreSQL table

Indexer.reindex_from_db()
  → reads all records from PostgreSQL and pushes to Meilisearch (no re-scraping)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterator, Optional

import psycopg2

from ingest.canonical.names import normalize_for_dedup
from ingest.checkpoints.store import CheckpointStore, connect_with_retry

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MEILI_INDEX_NAME = "parliamentary_records"
MEILI_BATCH_SIZE = 100

# Waits between retries of a failed Meilisearch push.
MEILI_RETRY_DELAYS = (5, 30, 120)
# raw_documents rows fetched per query in Stage 2 (keeps memory flat on big corpora).
RAW_DOC_CHUNK = 50

# Fields stored in PostgreSQL only; excluded from Meilisearch documents
_MEILI_EXCLUDED = frozenset({
    "page_reference",
    "has_untranslated_content",
    "session_number",
    "created_at",
    "dedup_key",
    "word_count",          # PostgreSQL-only per DATA-MODELS.md §2.2
    "lok_sabha_number",    # v3.0: detail-page-only (F09); excluded per §2.2
    "segments",            # v3.0: PostgreSQL-only (full_text_en carries search text)
    "canonical_doc_id",    # v3.0: serves F10 debug-raw lookup only
})

# JSONB columns requiring json.dumps before insert (psycopg2 adapts plain lists
# to ARRAY, not JSONB, so they must be serialized explicitly).
_JSONB_COLUMNS = frozenset({"segments"})

# All speeches-table columns (in INSERT order)
_SPEECH_COLUMNS = (
    "source", "proceeding_type", "date", "session_name", "session_number",
    "sitting_number", "subject", "speaker_name", "speaker_party",
    "speaker_constituency_or_state", "speaker_role", "sequence_within_sitting",
    "full_text_en", "lang_original", "time_of_day", "word_count",
    "is_translated", "has_untranslated_content",
    "speaker_name_unresolved", "source_url", "page_reference", "volume",
    "lok_sabha_number", "segments", "canonical_doc_id",
    "dedup_key",
)

# All qa_exchanges-table columns (in INSERT order)
_QA_COLUMNS = (
    "source", "proceeding_type", "date", "session_name", "session_number",
    "sitting_number", "question_number", "subject", "questioner_names",
    "questioner_party", "minister_name", "ministry",
    "sequence_within_sitting",
    "full_text_en", "lang_original", "time_of_day", "word_count",
    "is_translated", "has_untranslated_content",
    "source_url", "page_reference",
    "lok_sabha_number", "canonical_doc_id",
    "dedup_key",
)


def _insert_values(record: dict[str, Any], cols: tuple[str, ...]) -> tuple:
    """Build the ordered value tuple for an INSERT, serializing JSONB columns."""
    out = []
    for c in cols:
        v = record.get(c)
        if c in _JSONB_COLUMNS and v is not None:
            v = json.dumps(v, default=str)
        out.append(v)
    return tuple(out)


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
        doc[k] = _json_safe(v)
    return doc


def _json_safe(value: Any) -> Any:
    """Turn values read back from PostgreSQL into what a fresh record holds.

    reindex_from_db reads rows, so DATE comes back as datetime.date and UUID as
    uuid.UUID; Meilisearch needs the same ISO date / string forms as Stage 2.
    """
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _is_dead_connection(exc: Exception) -> bool:
    """True when a psycopg2 exception signals a dropped server-side connection."""
    if isinstance(exc, psycopg2.InterfaceError):
        return "connection already closed" in str(exc).lower()
    if not isinstance(exc, psycopg2.OperationalError):
        return False
    pgcode = getattr(exc, "pgcode", None)
    return pgcode is None or "server closed" in str(exc).lower()


# ── Indexer class ──────────────────────────────────────────────────────────────

class Indexer:
    """
    Writes canonical records to PostgreSQL and pushes to Meilisearch.

    Args:
        pg_conn:      psycopg2 connection (synchronous)
        meili_client: meilisearch.Client instance (synchronous)
    """

    def __init__(
        self,
        pg_conn: Any,
        meili_client: Any,
        pg_dsn: Optional[str] = None,
    ) -> None:
        self._pg = pg_conn
        self._pg_dsn = pg_dsn
        self._meili = meili_client
        self._meili_batch: list[dict] = []
        # Meilisearch indexing is asynchronous: keep task ids so failures can be
        # checked at the end of the run instead of passing silently.
        self._meili_task_ids: list[int] = []
        self.meili_failed_docs = 0

        # Counters for index_status
        self.counts: dict[str, int] = {"CA": 0, "LS": 0, "RS": 0}
        self.date_ranges: dict[str, list[str]] = {"CA": [], "LS": [], "RS": []}

    def _reconnect(self) -> None:
        """Replace self._pg with a fresh connection using the stored DSN."""
        if not self._pg_dsn:
            raise RuntimeError("No pg_dsn stored; cannot reconnect to PostgreSQL")
        try:
            self._pg.close()
        except Exception:
            pass
        self._pg = connect_with_retry(self._pg_dsn)
        logger.info("Reconnected to PostgreSQL after connection loss")

    def _execute_read(self, sql: str, params: tuple) -> Any:
        """
        Execute a read-only query, reconnecting and retrying once on a dead
        connection, and return the live cursor for the caller to fetch from.

        Long discovery/fetch phases can leave the server-side connection closed by
        the time a read fires; without this guard the read would raise instead of
        recovering the way the write methods do. The cursor is returned post-execute
        so callers keep their natural fetch pattern (fetchone for existence checks,
        fetchall for bulk reads).
        """
        try:
            cursor = self._pg.cursor()
            cursor.execute(sql, params)
            return cursor
        except Exception as exc:
            if _is_dead_connection(exc) and self._pg_dsn:
                logger.warning(
                    "Dead PG connection during read; reconnecting and retrying"
                )
                self._reconnect()
                cursor = self._pg.cursor()
                cursor.execute(sql, params)
                return cursor
            raise

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

        # No checkpoint-mirror short-circuit here: the ingestion_dedup_keys mirror
        # is a pre-filter only and must never suppress a legitimate insert
        # (ARCHITECTURE §8 item 7). The authoritative duplicate guard is the
        # UNIQUE(dedup_key) constraint on speeches/qa_exchanges, enforced below via
        # INSERT … ON CONFLICT (dedup_key) DO NOTHING. Relying on the mirror to skip
        # would wrongly drop rows on selective re-processing (a scope cleared from
        # speeches/qa_exchanges + processed_documents but not the dedup mirror).

        # Write to PostgreSQL
        record_with_key = dict(record, dedup_key=dedup_key)
        try:
            inserted = self._insert_record(record_with_key)
        except Exception as exc:
            if _is_dead_connection(exc) and self._pg_dsn:
                # Server-side timeout closed the connection; reconnect and retry once.
                logger.warning(
                    "Dead PG connection detected; reconnecting and retrying insert "
                    "(dedup_key=%s)",
                    dedup_key,
                )
                try:
                    self._reconnect()
                    inserted = self._insert_record(record_with_key)
                except Exception as retry_exc:
                    logger.warning(
                        "PG insert failed after reconnect for dedup_key=%s: %s; skipping",
                        dedup_key, retry_exc,
                    )
                    try:
                        self._pg.rollback()
                    except psycopg2.InterfaceError:
                        pass
                    return False
            else:
                # UniqueViolation or other constraint error: treat as duplicate.
                logger.warning(
                    "PG insert failed for dedup_key=%s: %s; skipping", dedup_key, exc
                )
                try:
                    self._pg.rollback()
                except psycopg2.InterfaceError:
                    pass
                return False

        if not inserted:
            return False

        # Mirror the dedup key into the pre-filter surface (corpus = record source).
        checkpoint.add_dedup_key(dedup_key, record.get("source", ""))
        if "id" in record:
            record_with_key["id"] = record["id"]
        self._after_insert(record_with_key)
        return True

    def next_sequence(self, source: str, date_val: Any, sitting_number: Any) -> int:
        """
        First free sequence_within_sitting for a sitting, given what is stored.

        Numbering continues from the records already written for the sitting, so
        a resumed or date-split run never reuses a position (which would also
        reuse a speech dedup key and silently drop the new record).
        """
        if not date_val:
            return 1
        cond = "sitting_number = %s" if sitting_number is not None else "sitting_number IS NULL"
        params: tuple = (source, date_val) + ((sitting_number,) if sitting_number is not None else ())
        sql = (
            "SELECT GREATEST("
            f"(SELECT max(sequence_within_sitting) FROM speeches WHERE source = %s AND date = %s AND {cond}), "
            f"(SELECT max(sequence_within_sitting) FROM qa_exchanges WHERE source = %s AND date = %s AND {cond}))"
        )
        row = self._execute_read(sql, params + params).fetchone()
        return int(row[0] or 0) + 1

    def index_document(
        self,
        records: list[dict[str, Any]],
        checkpoint: CheckpointStore,
        *,
        corpus: str,
        canonical_doc_id: str,
        provider: Optional[str] = None,
        fetch_url: Optional[str] = None,
    ) -> int:
        """
        Index every record of one document and mark the document processed.

        Records, their ingestion_dedup_keys mirror rows and the processed_documents
        row are written by one statement, so a crash leaves the document either
        fully stored or not at all (no half-written document to duplicate on
        resume), at two database round trips per document instead of about four
        per record. Returns the number of records inserted.

        A dead connection is reconnected and the statement retried. Any other
        error (one bad value, say) falls back to inserting record by record, so
        one record can't sink the whole document.
        """
        ready: list[dict[str, Any]] = []
        for record in records:
            if not record.get("date"):
                logger.error(
                    "Record missing date (source=%s, url=%s); skipping",
                    record.get("source"), record.get("source_url"),
                )
                continue
            ready.append(dict(record, dedup_key=build_dedup_key(record)))

        try:
            rows = self._insert_document(ready, corpus, canonical_doc_id, provider, fetch_url)
        except Exception as exc:
            try:
                self._pg.rollback()
            except Exception:
                pass
            if _is_dead_connection(exc) and self._pg_dsn:
                logger.warning(
                    "Dead PG connection while indexing %s; reconnecting and retrying",
                    canonical_doc_id,
                )
                self._reconnect()
                rows = self._insert_document(ready, corpus, canonical_doc_id, provider, fetch_url)
            else:
                logger.warning(
                    "Batch insert failed for %s (%s); inserting records one by one",
                    canonical_doc_id, exc,
                )
                inserted = sum(1 for r in records if self.index_record(r, checkpoint))
                checkpoint.mark_document_processed(
                    canonical_doc_id, corpus=corpus, provider=provider, fetch_url=fetch_url
                )
                return inserted

        ids = {key: rid for rid, key in rows}
        inserted = 0
        for record in ready:
            rid = ids.pop(record["dedup_key"], None)
            if rid is None:
                continue  # duplicate of a stored record (or of an earlier one here)
            record["id"] = str(rid)
            inserted += 1
            self._after_insert(record)
        return inserted

    def _insert_document(
        self,
        records: list[dict[str, Any]],
        corpus: str,
        canonical_doc_id: str,
        provider: Optional[str],
        fetch_url: Optional[str],
    ) -> list[tuple]:
        """Run the single INSERT statement for index_document; returns (id, dedup_key) rows."""
        cur = self._pg.cursor()

        def values(cols: tuple[str, ...], recs: list[dict]) -> str:
            row = "(" + ", ".join(["%s"] * len(cols)) + ")"
            return ", ".join(
                cur.mogrify(row, _insert_values(r, cols)).decode() for r in recs
            )

        parts: list[str] = []
        selects: list[str] = []
        for name, table, cols, kind in (
            ("s", "speeches", _SPEECH_COLUMNS, "speech"),
            ("q", "qa_exchanges", _QA_COLUMNS, "qa"),
        ):
            recs = [
                r for r in records
                if (r.get("record_type") == "qa") == (kind == "qa")
            ]
            if not recs:
                continue
            parts.append(
                f"{name} AS (INSERT INTO {table} ({', '.join(cols)}) VALUES {values(cols, recs)} "
                f"ON CONFLICT (dedup_key) DO NOTHING RETURNING id, dedup_key)"
            )
            selects.append(f"SELECT id, dedup_key FROM {name}")
        done = cur.mogrify(
            "INSERT INTO processed_documents (canonical_doc_id, corpus, provider, fetch_url) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (canonical_doc_id, corpus) DO NOTHING",
            (canonical_doc_id, corpus, provider, fetch_url),
        ).decode()
        if selects:
            corpus_lit = cur.mogrify("%s", (corpus,)).decode()
            parts.append(
                f"k AS (INSERT INTO ingestion_dedup_keys (dedup_key, corpus) "
                f"SELECT dedup_key, {corpus_lit} FROM ({' UNION ALL '.join(selects)}) n "
                f"ON CONFLICT (dedup_key, corpus) DO NOTHING)"
            )
            parts.append(f"p AS ({done})")
            sql = "WITH " + ", ".join(parts) + " " + " UNION ALL ".join(selects)
        else:
            sql = done
        # No parameters are passed: every value is already mogrified, so a "%"
        # inside speech text is not read as a placeholder.
        cur.execute(sql)
        rows = cur.fetchall() if selects else []
        self._pg.commit()
        return rows

    def _after_insert(self, record: dict[str, Any]) -> None:
        """Update run counters and queue the Meilisearch document for a stored record."""
        source = record.get("source", "")
        if source in self.counts:
            self.counts[source] += 1
            date_val = record.get("date")
            if date_val:
                self.date_ranges[source].append(str(date_val))
        doc = build_meili_document(record)
        if "id" in record:
            doc["id"] = record["id"]
        self._meili_batch.append(doc)
        if len(self._meili_batch) >= MEILI_BATCH_SIZE:
            self.flush()

    def _insert_record(self, record: dict[str, Any]) -> bool:
        """Insert record into the correct PostgreSQL table. Returns True on success."""
        record_type = record.get("record_type", "speech")
        cursor = self._pg.cursor()

        if record_type == "qa":
            return self._insert_qa(cursor, record)
        return self._insert_speech(cursor, record)

    def _insert_speech(self, cursor: Any, record: dict[str, Any]) -> bool:
        cols = _SPEECH_COLUMNS
        values = _insert_values(record, cols)
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
        values = _insert_values(record, cols)
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

    # ── Stage 1: raw document store ───────────────────────────────────────────

    def write_raw_document(
        self,
        canonical_doc_id: str,
        corpus: str,
        date: Optional[str],
        provider: str,
        format: str,
        extracted_text: Optional[str],
        metadata_json: dict,
        fetch_url: Optional[str],
        citation_url: Optional[str],
    ) -> None:
        """
        Insert a row into raw_documents (Stage 1 complete signal).

        No-op on PK conflict: if the document was already fetched in a prior
        Stage 1 run, the existing row is left untouched. This is the sole
        Stage 1 dedup guard — no SQLite checkpoint entry is written.
        """
        sql = """
            INSERT INTO raw_documents
                (canonical_doc_id, corpus, date, provider, format,
                 extracted_text, metadata_json, fetch_url, citation_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (canonical_doc_id, corpus) DO NOTHING
            """
        params = (
            canonical_doc_id,
            corpus,
            date,
            provider,
            format,
            extracted_text,
            json.dumps(metadata_json, default=str),
            fetch_url,
            citation_url,
        )
        try:
            cursor = self._pg.cursor()
            cursor.execute(sql, params)
            self._pg.commit()
        except Exception as exc:
            if _is_dead_connection(exc) and self._pg_dsn:
                logger.warning("Dead PG connection in write_raw_document; reconnecting")
                self._reconnect()
                cursor = self._pg.cursor()
                cursor.execute(sql, params)
                self._pg.commit()
            else:
                try:
                    self._pg.rollback()
                except psycopg2.InterfaceError:
                    pass
                raise
        logger.debug("write_raw_document: %s (corpus=%s)", canonical_doc_id, corpus)

    def check_raw_document_exists(self, canonical_doc_id: str, corpus: str) -> bool:
        """Return True if (canonical_doc_id, corpus) already exists in raw_documents."""
        cursor = self._execute_read(
            "SELECT 1 FROM raw_documents WHERE canonical_doc_id = %s AND corpus = %s",
            (canonical_doc_id, corpus),
        )
        return cursor.fetchone() is not None

    def read_raw_documents_for_scope(
        self,
        corpus: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        skip_ids: Optional[set[str]] = None,
    ) -> Iterator[dict]:
        """
        Yield raw_documents rows for *corpus*, optionally filtered by date range.

        Used by Stage 2 orchestrators to iterate over documents to process. Rows
        come in date order, then by handle number, so every run numbers a sitting's
        records the same way, and are read in chunks, so a corpus of hundreds of thousands of
        documents never sits in memory at once. Documents in *skip_ids* (already
        processed) are not read at all. metadata_json is returned as a dict.
        """
        params: list[Any] = [corpus]
        clauses = ["corpus = %s"]
        if date_from:
            clauses.append("date >= %s")
            params.append(date_from)
        if date_to:
            clauses.append("date <= %s")
            params.append(date_to)
        where = " AND ".join(clauses)
        ids = [
            r[0] for r in self._execute_read(
                f"SELECT canonical_doc_id FROM raw_documents WHERE {where} "
                f"ORDER BY date NULLS LAST, length(canonical_doc_id), canonical_doc_id",
                tuple(params),
            ).fetchall()
        ]
        if skip_ids:
            ids = [i for i in ids if i not in skip_ids]
        logger.info("%s: %d raw_documents rows to process", corpus.lower(), len(ids))
        for start in range(0, len(ids), RAW_DOC_CHUNK):
            chunk = ids[start:start + RAW_DOC_CHUNK]
            cursor = self._execute_read(
                "SELECT canonical_doc_id, corpus, date, provider, format, "
                "extracted_text, metadata_json, fetch_url, citation_url "
                "FROM raw_documents WHERE corpus = %s AND canonical_doc_id = ANY(%s)",
                (corpus, chunk),
            )
            columns = [desc[0] for desc in cursor.description]
            by_id = {}
            for row in cursor.fetchall():
                d = dict(zip(columns, row))
                # psycopg2 returns JSONB as a Python dict; normalise to dict if str
                if isinstance(d.get("metadata_json"), str):
                    d["metadata_json"] = json.loads(d["metadata_json"])
                if d["metadata_json"] is None:
                    d["metadata_json"] = {}
                by_id[d["canonical_doc_id"]] = d
            for doc_id in chunk:
                if doc_id in by_id:
                    yield by_id[doc_id]

    # ── Meilisearch flush ─────────────────────────────────────────────────────

    def flush(self) -> int:
        """Push buffered documents to Meilisearch. Returns number of documents pushed."""
        if not self._meili_batch:
            return 0
        batch = list(self._meili_batch)
        self._meili_batch.clear()
        for attempt, delay in enumerate((0,) + MEILI_RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                index = self._meili.index(MEILI_INDEX_NAME)
                task = index.add_documents(batch)
            except Exception as exc:
                if attempt < len(MEILI_RETRY_DELAYS):
                    logger.warning(
                        "Meilisearch push failed for %d documents (%s); retrying in %d s",
                        len(batch), exc, MEILI_RETRY_DELAYS[attempt],
                    )
                    continue
                self.meili_failed_docs += len(batch)
                logger.error("Meilisearch push failed for %d documents: %s", len(batch), exc)
                return len(batch)
            task_id = getattr(task, "task_uid", None)
            if isinstance(task_id, int):
                self._meili_task_ids.append(task_id)
            logger.debug("Pushed %d documents to Meilisearch", len(batch))
            break
        return len(batch)

    def verify_meili_tasks(self, timeout_in_ms: int | None = 600_000) -> list[str]:
        """
        Wait for every indexing task pushed in this run; return one message per
        failure (failed push, failed task, or a task that could not be checked).
        An empty list means everything pushed this run is searchable.
        """
        problems: list[str] = []
        if self.meili_failed_docs:
            problems.append(f"{self.meili_failed_docs} documents could not be sent to Meilisearch")
        for task_id in self._meili_task_ids:
            try:
                result = self._meili.wait_for_task(task_id, timeout_in_ms=timeout_in_ms)
            except Exception as exc:
                problems.append(f"task {task_id}: could not check status ({exc})")
                continue
            if getattr(result, "status", None) == "failed":
                problems.append(f"task {task_id}: {getattr(result, 'error', None)}")
        self._meili_task_ids.clear()
        return problems

    # ── index_status update ───────────────────────────────────────────────────

    def update_index_status(self) -> None:
        """Write one row to the index_status PostgreSQL table."""

        def _min_date(dates: list[str]) -> Optional[str]:
            return min(dates) if dates else None

        def _max_date(dates: list[str]) -> Optional[str]:
            return max(dates) if dates else None

        ca_dates = self.date_ranges.get("CA", [])
        ls_dates = self.date_ranges.get("LS", [])
        rs_dates = self.date_ranges.get("RS", [])

        sql = """
            INSERT INTO index_status (
                run_completed_at,
                total_records,
                ca_count, ca_date_from, ca_date_to,
                ls_count, ls_date_from, ls_date_to,
                rs_count, rs_date_from, rs_date_to
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        params = (
            datetime.now(timezone.utc),
            sum(self.counts.values()),
            self.counts.get("CA", 0), _min_date(ca_dates), _max_date(ca_dates),
            self.counts.get("LS", 0), _min_date(ls_dates), _max_date(ls_dates),
            self.counts.get("RS", 0), _min_date(rs_dates), _max_date(rs_dates),
        )
        try:
            cursor = self._pg.cursor()
            cursor.execute(sql, params)
            self._pg.commit()
        except Exception as exc:
            if _is_dead_connection(exc) and self._pg_dsn:
                logger.warning("Dead PG connection in update_index_status; reconnecting")
                self._reconnect()
                cursor = self._pg.cursor()
                cursor.execute(sql, params)
                self._pg.commit()
            else:
                try:
                    self._pg.rollback()
                except psycopg2.InterfaceError:
                    pass
                raise
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
        total = 0

        for table, record_type in (("speeches", "speech"), ("qa_exchanges", "qa")):
            cursor = self._execute_read(f"SELECT * FROM {table}", ())
            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
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
