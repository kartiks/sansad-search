"""Tests for ingest.indexer — dedup key construction, document building, indexing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch
import psycopg2
import pytest

from tests.fakes import FakeCheckpointStore as CheckpointStore
from ingest.indexer import (
    MEILI_BATCH_SIZE,
    Indexer,
    build_dedup_key,
    build_meili_document,
)
from ingest.segmenters.speech import segment_speeches


# ── build_dedup_key ───────────────────────────────────────────────────────────

class TestBuildDedupKey:
    def test_speech_key_format(self):
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "sitting_number": 5,
            "proceeding_type": "debate",
            "speaker_name": "Narendra Modi",
            "sequence_within_sitting": 3,
        }
        key = build_dedup_key(record)
        assert key == "LS_2023-03-15_5_debate_narendra_modi_3"

    def test_qa_key_format(self):
        record = {
            "record_type": "qa",
            "source": "RS",
            "date": "2023-03-15",
            "sitting_number": 2,
            "proceeding_type": "starred_question",
            "question_number": 42,
        }
        key = build_dedup_key(record)
        assert key == "RS_2023-03-15_2_starred_question_42"

    def test_same_member_different_sequence_produces_different_key(self):
        """Two speeches by the same member in the same sitting must have distinct keys."""
        base = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "sitting_number": 5,
            "proceeding_type": "debate",
            "speaker_name": "Narendra Modi",
        }
        key1 = build_dedup_key({**base, "sequence_within_sitting": 1})
        key2 = build_dedup_key({**base, "sequence_within_sitting": 2})
        assert key1 != key2

    def test_speaker_name_normalized_in_key(self):
        """Speaker name is normalized (lowercase, underscore) in the dedup key."""
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "sitting_number": 5,
            "proceeding_type": "debate",
            "speaker_name": "B. R. Ambedkar",
            "sequence_within_sitting": 1,
        }
        key = build_dedup_key(record)
        # B. R. Ambedkar → "b_r_ambedkar" (special chars stripped)
        assert "b_r_ambedkar" in key

    def test_none_speaker_name_uses_unknown(self):
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "sitting_number": 1,
            "proceeding_type": "debate",
            "speaker_name": None,
            "sequence_within_sitting": 1,
        }
        key = build_dedup_key(record)
        assert "unknown" in key

    def test_default_record_type_is_speech(self):
        """Records without record_type default to speech key format."""
        record = {
            "source": "CA",
            "date": "1947-01-01",
            "sitting_number": 1,
            "proceeding_type": "debate",
            "speaker_name": "Ambedkar",
            "sequence_within_sitting": 1,
        }
        key = build_dedup_key(record)
        assert "ambedkar" in key


# ── build_meili_document ──────────────────────────────────────────────────────

class TestBuildMeiliDocument:
    def test_excluded_fields_absent(self):
        record = {
            "source": "LS",
            "speaker_name": "Narendra Modi",
            "full_text_en": "Some speech text",
            "page_reference": 42,
            "has_untranslated_content": False,
            "session_number": 261,
            "created_at": "2023-01-01T00:00:00Z",
            "dedup_key": "some_key",
        }
        doc = build_meili_document(record)
        for field in ("page_reference", "has_untranslated_content",
                      "session_number", "created_at", "dedup_key"):
            assert field not in doc, f"{field} should be excluded from Meilisearch doc"

    def test_ocr_low_confidence_absent_from_schema(self):
        """ocr_low_confidence is dropped from speeches table in Phase 7."""
        from ingest.indexer import _SPEECH_COLUMNS, _MEILI_EXCLUDED
        assert "ocr_low_confidence" not in _SPEECH_COLUMNS, (
            "ocr_low_confidence must be absent from _SPEECH_COLUMNS after Phase 7 schema drop"
        )
        assert "ocr_low_confidence" not in _MEILI_EXCLUDED, (
            "ocr_low_confidence must be absent from _MEILI_EXCLUDED after Phase 7 schema drop"
        )

    def test_present_fields_included(self):
        record = {
            "source": "LS",
            "speaker_name": "Narendra Modi",
            "full_text_en": "Speech text",
            "proceeding_type": "debate",
        }
        doc = build_meili_document(record)
        assert doc["source"] == "LS"
        assert doc["speaker_name"] == "Narendra Modi"

    def test_none_values_omitted(self):
        """Fields with None values are omitted (not sent as null) per spec."""
        record = {
            "source": "LS",
            "speaker_name": None,
            "full_text_en": "Speech text",
        }
        doc = build_meili_document(record)
        assert "speaker_name" not in doc
        assert "full_text_en" in doc


# ── Indexer ───────────────────────────────────────────────────────────────────

def _make_speech_record(**overrides):
    base = {
        "record_type": "speech",
        "source": "LS",
        "proceeding_type": "debate",
        "date": "2023-03-15",
        "session_name": "Budget Session 2023",
        "session_number": 261,
        "sitting_number": 5,
        "subject": "General Discussion",
        "speaker_name": "Narendra Modi",
        "speaker_party": None,
        "speaker_constituency_or_state": None,
        "speaker_role": "member",
        "sequence_within_sitting": 1,
        "full_text_en": "The government has taken major steps.",
        "is_translated": False,
        "has_untranslated_content": False,
        "speaker_name_unresolved": False,
        "source_url": "https://sansad.in/doc.html",
        "page_reference": None,
        "volume": None,
    }
    base.update(overrides)
    return base


def _make_qa_record(**overrides):
    base = {
        "record_type": "qa",
        "source": "LS",
        "proceeding_type": "starred_question",
        "date": "2023-03-15",
        "session_name": "Budget Session 2023",
        "session_number": 261,
        "sitting_number": 5,
        "question_number": 42,
        "subject": "Road Safety",
        "questioner_names": ["Member A"],
        "questioner_party": None,
        "minister_name": "Minister B",
        "ministry": "Ministry of Roads",
        "full_text_en": "Question and answer text.",
        "is_translated": False,
        "has_untranslated_content": False,
        "source_url": "https://sansad.in/qa.html",
        "page_reference": None,
    }
    base.update(overrides)
    return base


def _make_mock_pg_conn(inserted=True):
    """Mock psycopg2 connection that returns a row (indicating INSERT succeeded)."""
    cursor = MagicMock()
    cursor.fetchone.return_value = ("some-uuid",) if inserted else None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _make_dedup_aware_pg_conn():
    """Mock PG conn simulating INSERT … ON CONFLICT (dedup_key) DO NOTHING RETURNING id.

    Tracks the dedup_keys it has "inserted" (the dedup_key is the last positional
    param of the indexer's INSERT). A first insert of a key returns a fresh id row;
    a repeat returns None (the ON CONFLICT no-op), exactly as the real UNIQUE
    constraint behaves. This is the authoritative dedup surface now that the
    indexer no longer short-circuits on the checkpoint mirror (§8 item 7).
    """
    seen: set[str] = set()
    state: dict = {"row": None}
    cursor = MagicMock()

    def _execute(sql, params=None):
        if params and "INSERT INTO" in sql and "RETURNING id" in sql:
            dedup_key = params[-1]
            if dedup_key in seen:
                state["row"] = None
            else:
                seen.add(dedup_key)
                state["row"] = (f"id-{len(seen)}",)
        return None

    cursor.execute.side_effect = _execute
    cursor.fetchone.side_effect = lambda: state["row"]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn._seen = seen  # exposed for assertions/inspection
    return conn


def _make_mock_meili():
    """Mock meilisearch.Client."""
    meili = MagicMock()
    index = MagicMock()
    meili.index.return_value = index
    return meili, index


class TestIndexerIndexRecord:
    def test_indexes_speech_record(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is True

    def test_skips_duplicate_via_on_conflict(self, tmp_path):
        """A record whose dedup key already exists is skipped by ON CONFLICT.

        The indexer no longer short-circuits on the checkpoint mirror (§8 item 7);
        the duplicate is caught by the UNIQUE(dedup_key) ON CONFLICT guard (here the
        dedup-aware mock returns no RETURNING row on the second insert).
        """
        pg = _make_dedup_aware_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            # First insert
            first = indexer.index_record(record, cp)
            # Second insert of identical record
            result = indexer.index_record(record, cp)

        assert first is True
        assert result is False

    def test_skips_record_with_missing_date(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(date=None)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is False

    def test_counts_incremented_per_source(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        r1 = _make_speech_record(source="LS", sequence_within_sitting=1)
        r2 = _make_speech_record(source="LS", sequence_within_sitting=2)
        r3 = _make_speech_record(source="RS", sequence_within_sitting=1,
                                 speaker_name="Other Member")

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(r1, cp)
            indexer.index_record(r2, cp)
            indexer.index_record(r3, cp)

        assert indexer.counts["LS"] == 2
        assert indexer.counts["RS"] == 1

    def test_same_member_twice_in_same_sitting_indexed_separately(self, tmp_path):
        """
        Two speeches by the same member in the same sitting must produce two
        separate records with distinct dedup keys (different sequence_within_sitting).
        """
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        r1 = _make_speech_record(sequence_within_sitting=1)
        r2 = _make_speech_record(sequence_within_sitting=2)  # same speaker, same sitting

        with CheckpointStore(tmp_path / "cp.db") as cp:
            ok1 = indexer.index_record(r1, cp)
            ok2 = indexer.index_record(r2, cp)

        assert ok1 is True
        assert ok2 is True
        assert indexer.counts["LS"] == 2

    def test_qa_record_indexed(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_qa_record()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is True

    def test_pg_insert_failure_calls_rollback(self, tmp_path):
        # When cursor.execute raises (e.g. NOT NULL constraint from proceeding_type=None
        # hitting the DB), rollback() must be called so subsequent inserts on the same
        # connection are not aborted by a lingering failed transaction.
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("NOT NULL constraint violation")
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is False
        pg.rollback.assert_called_once()

    def test_subsequent_insert_succeeds_after_failed_insert(self, tmp_path):
        # After a failed insert (which triggers rollback), the next record must be
        # indexed successfully — verifies there is no cascade-abort on the connection.
        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("simulated constraint error")
            # subsequent calls succeed (default MagicMock behaviour)

        cursor = MagicMock()
        cursor.execute.side_effect = execute_side_effect
        cursor.fetchone.return_value = ("uuid-second",)
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        r1 = _make_speech_record(sequence_within_sitting=1)
        r2 = _make_speech_record(sequence_within_sitting=2)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result1 = indexer.index_record(r1, cp)
            result2 = indexer.index_record(r2, cp)

        assert result1 is False   # first record failed
        assert result2 is True    # second record indexed despite prior failure
        pg.rollback.assert_called_once()  # rollback called exactly once (after failure)


class TestIndexerFlush:
    def test_flush_sends_batch_to_meilisearch(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, index_mock = _make_mock_meili()
        indexer = Indexer(pg, meili)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(_make_speech_record(sequence_within_sitting=1), cp)
            indexer.index_record(_make_speech_record(sequence_within_sitting=2), cp)
            count = indexer.flush()

        assert count == 2
        index_mock.add_documents.assert_called_once()
        docs = index_mock.add_documents.call_args[0][0]
        assert len(docs) == 2

    def test_flush_empty_batch_returns_zero(self, tmp_path):
        pg = _make_mock_pg_conn()
        meili, index_mock = _make_mock_meili()
        indexer = Indexer(pg, meili)
        assert indexer.flush() == 0
        index_mock.add_documents.assert_not_called()

    def test_auto_flush_on_batch_size(self, tmp_path):
        """Batch is flushed automatically when it reaches MEILI_BATCH_SIZE."""
        pg = _make_mock_pg_conn(inserted=True)
        meili, index_mock = _make_mock_meili()
        indexer = Indexer(pg, meili)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            for i in range(MEILI_BATCH_SIZE):
                indexer.index_record(
                    _make_speech_record(sequence_within_sitting=i + 1,
                                        speaker_name=f"Member {i}"),
                    cp,
                )

        # Auto-flush should have been triggered
        assert index_mock.add_documents.call_count >= 1


class TestIndexerResumeability:
    def test_rerun_produces_zero_new_records(self, tmp_path):
        """
        Running the indexer twice against the same corpus produces zero new
        records on the second run.
        """
        # Both runs share one PostgreSQL "database" (one dedup-aware conn), so the
        # second run's inserts hit ON CONFLICT and produce zero new records — this
        # is the record-level resumability guarantee (INF-R1) now that dedup is in
        # PostgreSQL, not the checkpoint mirror.
        pg = _make_dedup_aware_pg_conn()

        # First run
        meili, _ = _make_mock_meili()
        indexer1 = Indexer(pg, meili)

        records = [
            _make_speech_record(sequence_within_sitting=i + 1, speaker_name=f"Member {i}")
            for i in range(5)
        ]

        with CheckpointStore(tmp_path / "cp.db") as cp:
            for r in records:
                indexer1.index_record(r, cp)
            first_count = indexer1.counts["LS"]

        # Second run (same database)
        meili2, _ = _make_mock_meili()
        indexer2 = Indexer(pg, meili2)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            for r in records:
                indexer2.index_record(r, cp)
            second_count = indexer2.counts["LS"]

        assert first_count == 5
        assert second_count == 0  # all already present (ON CONFLICT)

    def test_interrupted_then_resumed_matches_clean_run(self, tmp_path):
        """
        An interrupted run (records 0-2) followed by a resumed run over the full
        corpus (records 0-4) must produce the same total indexed count as a single
        clean run over the full corpus.
        """
        records = [
            _make_speech_record(sequence_within_sitting=i + 1, speaker_name=f"Member {i}")
            for i in range(5)
        ]

        # Interrupted + resumed share one PostgreSQL "database" (one dedup-aware
        # conn); the clean run uses a fresh database.
        pg_resume = _make_dedup_aware_pg_conn()

        # ── Interrupted run: index records 0-2 only, then "crash" ─────────────
        meili1, _ = _make_mock_meili()
        indexer1 = Indexer(pg_resume, meili1)
        with CheckpointStore(tmp_path / "cp.db") as cp:
            for r in records[:3]:
                indexer1.index_record(r, cp)
        interrupted_count = sum(indexer1.counts.values())
        assert interrupted_count == 3

        # ── Resumed run: same database, process full corpus ────────────────────
        meili2, _ = _make_mock_meili()
        indexer2 = Indexer(pg_resume, meili2)
        with CheckpointStore(tmp_path / "cp.db") as cp:
            for r in records:  # all 5
                indexer2.index_record(r, cp)
        resumed_count = sum(indexer2.counts.values())
        # Records 0-2 already present (ON CONFLICT); only 3 and 4 should be new
        assert resumed_count == 2

        # ── Clean run: fresh database, index all 5 ─────────────────────────────
        pg_clean = _make_dedup_aware_pg_conn()
        meili3, _ = _make_mock_meili()
        indexer3 = Indexer(pg_clean, meili3)
        with CheckpointStore(tmp_path / "clean_cp.db") as cp:
            for r in records:
                indexer3.index_record(r, cp)
        clean_count = sum(indexer3.counts.values())

        # Total of interrupted + resumed must equal the clean run
        assert interrupted_count + resumed_count == clean_count


class TestIndexerConnectionResilience:
    """Tests for PostgreSQL connection timeout recovery (Bug 1 + Bug 2)."""

    def test_interface_error_in_rollback_does_not_crash(self, tmp_path):
        """
        Bug 1: rollback() raising InterfaceError (connection already closed) must be
        swallowed — the process must not crash and the record must be skipped.
        """
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("NOT NULL constraint violation")
        pg = MagicMock()
        pg.cursor.return_value = cursor
        pg.rollback.side_effect = psycopg2.InterfaceError("connection already closed")
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is False  # record skipped — no crash

    def test_operational_error_triggers_reconnect_and_retry(self, tmp_path):
        """
        Bug 2: OperationalError with pgcode=None (dead connection) must trigger
        _reconnect() and retry the insert; subsequent records must succeed.
        """
        dead_error = psycopg2.OperationalError(
            "server closed the connection unexpectedly"
        )
        # pgcode is None by default on manually constructed OperationalError

        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_cursor.fetchone.return_value = ("recovered-uuid",)
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, _ = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)
        record = _make_speech_record()

        with patch("psycopg2.connect", return_value=new_conn) as mock_connect:
            with CheckpointStore(tmp_path / "cp.db") as cp:
                result = indexer.index_record(record, cp)

        mock_connect.assert_called_once_with(dsn)
        assert result is True, "Insert must succeed after reconnect"
        assert indexer._pg is new_conn, "Indexer must hold the new connection after reconnect"

    def test_interface_error_triggers_reconnect_and_retry(self, tmp_path):
        """
        InterfaceError("connection already closed") on _insert_record must trigger
        _reconnect() and retry, parallel to the OperationalError path.
        """
        dead_error = psycopg2.InterfaceError("connection already closed")

        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_cursor.fetchone.return_value = ("recovered-uuid",)
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, _ = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)
        record = _make_speech_record()

        with patch("psycopg2.connect", return_value=new_conn) as mock_connect:
            with CheckpointStore(tmp_path / "cp.db") as cp:
                result = indexer.index_record(record, cp)

        mock_connect.assert_called_once_with(dsn)
        assert result is True, "Insert must succeed after reconnect"
        assert indexer._pg is new_conn, "Indexer must hold the new connection after reconnect"

    def test_update_index_status_reconnects_on_dead_connection(self):
        """
        update_index_status must reconnect and retry the INSERT when the connection
        was dropped between the last flush() and the final status write.
        """
        dead_error = psycopg2.OperationalError(
            "server closed the connection unexpectedly"
        )

        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, _ = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)
        indexer.counts = {"CA": 5, "LS": 10, "RS": 3}
        indexer.date_ranges = {
            "CA": ["1947-01-01", "1950-11-26"],
            "LS": ["2023-01-01", "2023-12-31"],
            "RS": ["2019-01-01"],
        }

        with patch("psycopg2.connect", return_value=new_conn):
            indexer.update_index_status()  # must not raise

        new_cursor.execute.assert_called_once()
        assert "INSERT INTO index_status" in new_cursor.execute.call_args[0][0]
        new_conn.commit.assert_called_once()

    def test_check_raw_document_exists_reconnects_on_dead_connection(self):
        """
        check_raw_document_exists is the Stage 1 dedup read fired during long
        discovery phases; a connection dropped mid-phase must reconnect and retry,
        not raise.
        """
        dead_error = psycopg2.OperationalError(
            "server closed the connection unexpectedly"
        )
        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_cursor.fetchone.return_value = (1,)
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, _ = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)

        with patch("psycopg2.connect", return_value=new_conn) as mock_connect:
            result = indexer.check_raw_document_exists("doc-1", "LS")

        mock_connect.assert_called_once_with(dsn)
        assert result is True, "Existence check must succeed (True) after reconnect"
        assert indexer._pg is new_conn

    def test_read_raw_documents_for_scope_reconnects_on_dead_connection(self):
        """
        read_raw_documents_for_scope (Stage 2 iteration) must reconnect and retry
        once when the connection was dropped, yielding the recovered rows.
        """
        dead_error = psycopg2.OperationalError(
            "server closed the connection unexpectedly"
        )
        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_cursor.description = [
            ("canonical_doc_id",), ("corpus",), ("date",), ("provider",),
            ("format",), ("extracted_text",), ("metadata_json",),
            ("fetch_url",), ("citation_url",),
        ]
        new_cursor.fetchall.return_value = [
            ("doc-1", "LS", "2023-01-01", "ia", "ia_text", "body",
             {"k": "v"}, "https://fetch", "https://cite"),
        ]
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, _ = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)

        with patch("psycopg2.connect", return_value=new_conn) as mock_connect:
            results = list(indexer.read_raw_documents_for_scope("LS"))

        mock_connect.assert_called_once_with(dsn)
        assert len(results) == 1
        assert results[0]["canonical_doc_id"] == "doc-1"
        assert results[0]["metadata_json"] == {"k": "v"}
        assert indexer._pg is new_conn

    def test_reindex_from_db_reconnects_on_dead_connection(self):
        """
        reindex_from_db reads the full corpus from PostgreSQL; a dropped connection
        on the first SELECT must reconnect and complete the re-index.
        """
        dead_error = psycopg2.OperationalError(
            "server closed the connection unexpectedly"
        )
        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = dead_error
        dead_conn = MagicMock()
        dead_conn.cursor.return_value = dead_cursor

        new_cursor = MagicMock()
        new_cursor.description = [("id",), ("source",), ("full_text_en",), ("date",)]
        # First call (speeches) yields one row; second call (qa_exchanges) yields none.
        new_cursor.fetchall.side_effect = [
            [("u1", "LS", "speech text", "2023-01-01")],
            [],
        ]
        new_conn = MagicMock()
        new_conn.cursor.return_value = new_cursor

        meili, index = _make_mock_meili()
        dsn = "postgresql://localhost/testdb"
        indexer = Indexer(dead_conn, meili, pg_dsn=dsn)

        with patch("psycopg2.connect", return_value=new_conn) as mock_connect:
            total = indexer.reindex_from_db()

        mock_connect.assert_called_once_with(dsn)
        assert total == 1, "The one recovered speech must be pushed to Meilisearch"
        index.add_documents.assert_called_once()
        assert indexer._pg is new_conn

    def test_read_propagates_non_dead_connection_error(self):
        """
        A read failure that is NOT a dead-connection signal must propagate, not be
        silently swallowed or retried.
        """
        cursor = MagicMock()
        cursor.execute.side_effect = psycopg2.ProgrammingError("syntax error at or near")
        pg = MagicMock()
        pg.cursor.return_value = cursor

        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili, pg_dsn="postgresql://localhost/testdb")

        with patch("psycopg2.connect") as mock_connect:
            with pytest.raises(psycopg2.ProgrammingError):
                indexer.check_raw_document_exists("doc-1", "LS")
        mock_connect.assert_not_called()  # no reconnect attempted for a non-dead error


class TestIndexerUpdateStatus:
    def test_update_index_status_inserts_row(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.counts = {"CA": 100, "LS": 500, "RS": 300}
        indexer.date_ranges = {
            "CA": ["1946-12-09", "1950-11-26"],
            "LS": ["2014-06-04", "2023-03-15"],
            "RS": ["2014-06-11", "2023-03-15"],
        }
        indexer.update_index_status()

        cursor = pg.cursor()
        # SQL must reference the correct table
        sql = cursor.execute.call_args[0][0]
        assert "INSERT INTO index_status" in sql

        # Parameters tuple must carry the right counts and total
        params = cursor.execute.call_args[0][1]
        # params[0] is run_completed_at (datetime)
        assert params[1] == 900, f"total_records must be 900 (100+500+300), got {params[1]}"
        assert params[2] == 100, f"ca_count must be 100, got {params[2]}"
        assert params[5] == 500, f"ls_count must be 500, got {params[5]}"
        assert params[8] == 300, f"rs_count must be 300, got {params[8]}"


class TestIndexerReindexFromDb:
    def test_reindex_pushes_all_speeches_and_qa(self):
        """
        reindex_from_db reads all rows from both tables and pushes every record
        to Meilisearch with excluded fields absent from the pushed documents.
        """
        speech_cols = [
            "id", "source", "proceeding_type", "date", "session_name", "session_number",
            "sitting_number", "subject", "speaker_name", "speaker_party",
            "speaker_constituency_or_state", "speaker_role", "sequence_within_sitting",
            "full_text_en", "is_translated", "has_untranslated_content",
            "speaker_name_unresolved", "source_url", "page_reference", "volume",
            "dedup_key", "created_at",
        ]
        qa_cols = [
            "id", "source", "proceeding_type", "date", "session_name", "session_number",
            "sitting_number", "question_number", "subject", "questioner_names",
            "questioner_party", "minister_name", "ministry",
            "full_text_en", "is_translated", "has_untranslated_content",
            "source_url", "page_reference", "dedup_key", "created_at",
        ]

        def _speech_row(idx):
            return (
                f"uuid-{idx}", "LS", "debate", "2023-03-15", None, 261, 5, None,
                f"Member {idx}", None, None, "member", idx, "Speech text",
                False, False, False,
                "https://sansad.in/doc.html", None, None,
                f"dedup_{idx}", "2023-01-01",
            )

        def _qa_row(idx):
            return (
                f"uuid-qa-{idx}", "LS", "starred_question", "2023-03-15", None, 261, 5,
                idx, None, ["Member A"], None, "Minister", "Ministry",
                "Q&A text", False, False,
                "https://sansad.in/qa.html", None, f"qa_dedup_{idx}", "2023-01-01",
            )

        speech_rows = [_speech_row(1), _speech_row(2)]
        qa_rows = [_qa_row(1), _qa_row(2)]

        cursor = MagicMock()

        def fake_execute(sql, *args):
            if "speeches" in sql:
                cursor.description = [(col, None) for col in speech_cols]
            else:
                cursor.description = [(col, None) for col in qa_cols]

        cursor.execute.side_effect = fake_execute
        cursor.fetchall.side_effect = [speech_rows, qa_rows]

        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, index_mock = _make_mock_meili()

        indexer = Indexer(pg, meili)
        total = indexer.reindex_from_db()

        assert total == 4, f"Expected 4 total (2 speeches + 2 QA), got {total}"

        # Collect all documents pushed across all add_documents calls
        pushed_docs: list = []
        for call_args in index_mock.add_documents.call_args_list:
            pushed_docs.extend(call_args[0][0])

        assert len(pushed_docs) == 4

        # Excluded fields must be absent from every pushed document
        excluded = {
            "page_reference", "has_untranslated_content",
            "session_number", "created_at", "dedup_key",
        }
        for doc in pushed_docs:
            for field in excluded:
                assert field not in doc, (
                    f"Excluded field '{field}' must not appear in Meilisearch document"
                )


# ── Language handling integration ─────────────────────────────────────────────

class TestLanguageHandlingIntegration:
    def test_is_translated_false_for_english(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(is_translated=False, full_text_en="English text")

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        # Check that the INSERT was called with is_translated=False
        cursor = pg.cursor()
        args = cursor.execute.call_args[0][1]
        # Find the is_translated position in the tuple
        from ingest.indexer import _SPEECH_COLUMNS
        idx = list(_SPEECH_COLUMNS).index("is_translated")
        assert args[idx] is False

    def test_has_untranslated_content_true_for_hindi_only(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(
            full_text_en=None,
            has_untranslated_content=True,
            is_translated=False,
        )

        with CheckpointStore(tmp_path / "cp.db") as cp:
            result = indexer.index_record(record, cp)

        assert result is True  # Hindi-only records are still indexed

    def test_is_translated_true_for_hindi_with_translation(self, tmp_path):
        """Case 2: Hindi speech with English translation → is_translated=True in INSERT."""
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(
            is_translated=True,
            full_text_en="The translated English text of the speech.",
            has_untranslated_content=False,
            sequence_within_sitting=2,
        )

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        from ingest.indexer import _SPEECH_COLUMNS
        cursor = pg.cursor()
        args = cursor.execute.call_args[0][1]
        cols = list(_SPEECH_COLUMNS)

        assert args[cols.index("is_translated")] is True
        assert args[cols.index("has_untranslated_content")] is False
        assert args[cols.index("full_text_en")] == "The translated English text of the speech."

    def test_bilingual_speech_is_translated_true_with_full_text(self, tmp_path):
        """Case 3: Bilingual speech → is_translated=True and full_text_en carries both portions."""
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        full_text = "Original English opening statement. Translated Hindi portion follows."
        record = _make_speech_record(
            is_translated=True,
            full_text_en=full_text,
            has_untranslated_content=False,
            sequence_within_sitting=3,
        )

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        from ingest.indexer import _SPEECH_COLUMNS
        cursor = pg.cursor()
        args = cursor.execute.call_args[0][1]
        cols = list(_SPEECH_COLUMNS)

        assert args[cols.index("is_translated")] is True
        assert args[cols.index("full_text_en")] == full_text, (
            "Bilingual record must store full_text_en containing both English and translated portions"
        )
        assert args[cols.index("full_text_en")] is not None


# ── Unattributed speech ───────────────────────────────────────────────────────

class TestUnattributedSpeech:
    def test_dedup_key_handles_none_speaker_name(self):
        """build_dedup_key must not raise when speaker_name is None; uses 'unknown'."""
        record = _make_speech_record(speaker_name=None)
        key = build_dedup_key(record)
        assert "unknown" in key

    def test_segmenter_excludes_unattributed_speech(self):
        """
        The speech segmenter is the boundary that excludes unattributed speakers
        ('SEVERAL HON. MEMBERS', 'AN HON. MEMBER', etc.).  A document containing
        only unattributed speech must produce zero records.
        """
        raw_record = {
            "raw_text": (
                "SEVERAL HON. MEMBERS :\n"
                "Hear, hear!\n\n"
                "AN HON. MEMBER :\n"
                "Here!\n"
            ),
            "date": "2023-03-15",
            "source_url": "https://sansad.in/test.html",
            "proceeding_type": "debate",
        }
        speeches = segment_speeches(raw_record, "LS")
        assert len(speeches) == 0, (
            "Unattributed speakers must be excluded by the segmenter; "
            f"got {len(speeches)} record(s)"
        )


# ── Phase 10: Meilisearch exclusions and new fields ───────────────────────────

class TestMeilisearchFieldsV2:
    def test_word_count_excluded_from_meili_document(self):
        """word_count is PostgreSQL-only — must not appear in Meilisearch push."""
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "proceeding_type": "debate",
            "speaker_name": "Test Speaker",
            "full_text_en": "A speech with some words.",
            "lang_original": "en",
            "time_of_day": "14:00",
            "word_count": 5,
            "is_translated": False,
            "has_untranslated_content": False,
            "speaker_name_unresolved": False,
            "sequence_within_sitting": 1,
            "dedup_key": "LS_2023-03-15_1_debate_test_speaker_1",
        }
        doc = build_meili_document(record)
        assert "word_count" not in doc, (
            "word_count is PostgreSQL-only and must not appear in Meilisearch document"
        )

    def test_lang_original_included_in_meili_document(self):
        """lang_original must be present in Meilisearch document for F05 badge."""
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "proceeding_type": "debate",
            "lang_original": "en",
            "time_of_day": None,
            "word_count": 5,
            "is_translated": False,
            "dedup_key": "test",
        }
        doc = build_meili_document(record)
        assert "lang_original" in doc
        assert doc["lang_original"] == "en"

    def test_time_of_day_included_in_meili_document_when_not_none(self):
        """time_of_day is included in Meilisearch document when present."""
        record = {
            "record_type": "speech",
            "source": "RS",
            "date": "2023-03-15",
            "lang_original": "en",
            "time_of_day": "11:30",
            "word_count": 3,
            "dedup_key": "test",
        }
        doc = build_meili_document(record)
        assert "time_of_day" in doc
        assert doc["time_of_day"] == "11:30"

    def test_time_of_day_omitted_from_meili_document_when_none(self):
        """None fields are omitted from Meilisearch document (no null-padding)."""
        record = {
            "record_type": "speech",
            "source": "LS",
            "date": "2023-03-15",
            "lang_original": "en",
            "time_of_day": None,
            "word_count": None,
            "dedup_key": "test",
        }
        doc = build_meili_document(record)
        assert "time_of_day" not in doc

    def test_qa_sequence_within_sitting_in_meili_document(self):
        """Q+A records carry sequence_within_sitting in Meilisearch document (new in v2.0)."""
        record = {
            "record_type": "qa",
            "source": "LS",
            "date": "2023-03-15",
            "proceeding_type": "starred_question",
            "questioner_names": ["Shri Test"],
            "lang_original": "en",
            "time_of_day": None,
            "word_count": 10,
            "sequence_within_sitting": 3,
            "is_translated": False,
            "dedup_key": "test",
        }
        doc = build_meili_document(record)
        assert "sequence_within_sitting" in doc
        assert doc["sequence_within_sitting"] == 3


# ── Phase 13: v3.0 columns (lok_sabha_number, segments, canonical_doc_id) ──────

class TestV3Columns:
    def test_v3_fields_excluded_from_meili_document(self):
        record = {
            "source": "LS",
            "speaker_name": "Narendra Modi",
            "full_text_en": "Speech text",
            "lok_sabha_number": 17,
            "segments": [{"text": "Speech text", "segment_index": 0}],
            "canonical_doc_id": "123456",
        }
        doc = build_meili_document(record)
        for field in ("lok_sabha_number", "segments", "canonical_doc_id"):
            assert field not in doc, f"{field} must be excluded from the Meilisearch doc"

    def test_v3_columns_present_in_speech_columns(self):
        from ingest.indexer import _SPEECH_COLUMNS
        for col in ("lok_sabha_number", "segments", "canonical_doc_id"):
            assert col in _SPEECH_COLUMNS

    def test_v3_columns_present_in_qa_columns(self):
        from ingest.indexer import _QA_COLUMNS
        for col in ("lok_sabha_number", "canonical_doc_id"):
            assert col in _QA_COLUMNS
        # segments is a speeches-only column
        assert "segments" not in _QA_COLUMNS

    def test_speech_insert_writes_v3_fields_to_pg(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(
            lok_sabha_number=17,
            segments=[
                {"text": "First.", "segment_index": 0},
                {"text": "Second.", "segment_index": 1},
            ],
            canonical_doc_id="123456",
        )

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        # Inspect the INSERT executed against the mock cursor.
        cursor = pg.cursor.return_value
        sql, values = cursor.execute.call_args[0]
        assert "INSERT INTO speeches" in sql
        assert "lok_sabha_number" in sql
        assert "canonical_doc_id" in sql
        assert "segments" in sql
        assert 17 in values
        assert "123456" in values
        # segments is serialized to a JSON string (psycopg2 adapts lists to ARRAY).
        seg_json = next(v for v in values if isinstance(v, str) and v.startswith("[") and "segment_index" in v)
        import json as _json
        assert _json.loads(seg_json)[1]["segment_index"] == 1

    def test_qa_insert_writes_v3_fields_to_pg(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_qa_record(lok_sabha_number=17, canonical_doc_id="998877")

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        cursor = pg.cursor.return_value
        sql, values = cursor.execute.call_args[0]
        assert "INSERT INTO qa_exchanges" in sql
        assert "lok_sabha_number" in sql
        assert "canonical_doc_id" in sql
        assert 17 in values
        assert "998877" in values

    def test_segments_none_passed_as_none_not_serialized(self, tmp_path):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        record = _make_speech_record(segments=None, lok_sabha_number=None, canonical_doc_id=None)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            indexer.index_record(record, cp)

        cursor = pg.cursor.return_value
        _, values = cursor.execute.call_args[0]
        # No accidental "null" string serialization for a None segments value.
        assert "null" not in [v for v in values if isinstance(v, str)]
