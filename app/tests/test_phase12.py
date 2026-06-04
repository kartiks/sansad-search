"""
Phase 12 tests: two-stage pipeline and raw_documents store.

Test requirements (from PHASES.md phase-12 stop conditions):
- schema.sql creates raw_documents table and idx_raw_documents_corpus_date index
- indexer.write_raw_document() inserts a row (no-op on PK conflict)
- indexer.check_raw_document_exists() returns True for existing id, False for absent
- --stage fetch writes exactly one raw_documents row per document (via mocked providers)
- --stage process reads mocked raw_documents rows and produces correct records
- Stage 1 re-run writes zero new rows (PK dedup skips all)
- Stage 2 re-run after interruption resumes from SQLite processed_documents checkpoint
- --stage process --date-from / --date-to reads only matching date range
- --stage all produces identical final state to fetch then process separately
- All existing Phase 1–11 tests pass without modification (no imports from removed items)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest import main as main_mod


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_pg_conn(inserted=True):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("some-uuid",) if inserted else None
    cursor.description = [("canonical_doc_id", None)]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def _make_mock_meili():
    meili = MagicMock()
    index = MagicMock()
    meili.index.return_value = index
    return meili, index


# ── Schema: raw_documents table ──────────────────────────────────────────────

class TestSchemaRawDocuments:
    SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

    def test_raw_documents_table_exists_in_schema(self):
        content = self.SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS raw_documents" in content

    def test_raw_documents_has_canonical_doc_id_pk(self):
        content = self.SCHEMA_PATH.read_text()
        raw_block = content.split("CREATE TABLE IF NOT EXISTS raw_documents")[1].split(");")[0]
        assert "canonical_doc_id" in raw_block
        assert "PRIMARY KEY" in raw_block

    def test_raw_documents_corpus_check_constraint(self):
        content = self.SCHEMA_PATH.read_text()
        raw_block = content.split("CREATE TABLE IF NOT EXISTS raw_documents")[1].split(");")[0]
        assert "'CA'" in raw_block
        assert "'LS'" in raw_block
        assert "'RS'" in raw_block

    def test_raw_documents_format_check_constraint(self):
        content = self.SCHEMA_PATH.read_text()
        raw_block = content.split("CREATE TABLE IF NOT EXISTS raw_documents")[1].split(");")[0]
        assert "'html'" in raw_block
        assert "'ia_text'" in raw_block
        assert "'pdf'" in raw_block

    def test_raw_documents_has_required_columns(self):
        content = self.SCHEMA_PATH.read_text()
        for col in ("corpus", "date", "provider", "format", "extracted_text",
                    "metadata_json", "fetch_url", "citation_url", "fetched_at"):
            assert col in content, f"Missing column: {col}"

    def test_raw_documents_corpus_date_index_exists(self):
        content = self.SCHEMA_PATH.read_text()
        assert "idx_raw_documents_corpus_date" in content
        assert "raw_documents(corpus, date)" in content


# ── Indexer Stage 1 methods ───────────────────────────────────────────────────

class TestIndexerWriteRawDocument:
    def test_write_raw_document_calls_pg_insert(self):
        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        indexer.write_raw_document(
            canonical_doc_id="test-doc-1",
            corpus="CA",
            date="1946-12-09",
            provider="coi_html",
            format="html",
            extracted_text="Some speech text...",
            metadata_json={"source": "CA", "date": "1946-12-09"},
            fetch_url="https://www.constitutionofindia.net/debates/1946-12-09",
            citation_url="https://www.constitutionofindia.net/debates/1946-12-09",
        )

        cursor = pg.cursor()
        sql = cursor.execute.call_args[0][0]
        assert "INSERT INTO raw_documents" in sql
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    def test_write_raw_document_serializes_metadata_as_json(self):
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        metadata = {"source": "LS", "proceeding_type": "debate", "sitting_number": 5}
        indexer.write_raw_document(
            canonical_doc_id="12345",
            corpus="LS",
            date="2023-03-15",
            provider="internet_archive",
            format="ia_text",
            extracted_text="Text content",
            metadata_json=metadata,
            fetch_url="https://archive.org/...",
            citation_url="https://eparlib.sansad.in/...",
        )

        cursor = pg.cursor()
        params = cursor.execute.call_args[0][1]
        # params[6] is metadata_json — must be a JSON string
        assert isinstance(params[6], str)
        parsed = json.loads(params[6])
        assert parsed["proceeding_type"] == "debate"
        assert parsed["sitting_number"] == 5

    def test_write_raw_document_null_extracted_text_allowed(self):
        """Text-less PDFs write a row with null extracted_text (row records the fetch)."""
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        indexer.write_raw_document(
            canonical_doc_id="pdf-textless-1",
            corpus="LS",
            date="2020-01-15",
            provider="eparlib_dspace",
            format="pdf",
            extracted_text=None,
            metadata_json={},
            fetch_url="https://eparlib.sansad.in/...",
            citation_url=None,
        )

        cursor = pg.cursor()
        params = cursor.execute.call_args[0][1]
        assert params[5] is None  # extracted_text is null

    def test_write_raw_document_commits_transaction(self):
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        indexer.write_raw_document(
            canonical_doc_id="any-id",
            corpus="RS",
            date=None,
            provider="sansad_rs_html",
            format="html",
            extracted_text=None,
            metadata_json={},
            fetch_url=None,
            citation_url=None,
        )
        pg.commit.assert_called()


class TestIndexerCheckRawDocumentExists:
    def test_returns_true_for_existing_doc(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        result = indexer.check_raw_document_exists("existing-doc")
        assert result is True

    def test_returns_false_for_absent_doc(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        result = indexer.check_raw_document_exists("absent-doc")
        assert result is False

    def test_uses_pk_lookup_query(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        indexer.check_raw_document_exists("some-id")
        sql = cursor.execute.call_args[0][0]
        assert "raw_documents" in sql
        assert "canonical_doc_id" in sql


class TestIndexerReadRawDocumentsForScope:
    def _make_pg_with_rows(self, rows, columns=None):
        if columns is None:
            columns = [
                "canonical_doc_id", "corpus", "date", "provider", "format",
                "extracted_text", "metadata_json", "fetch_url", "citation_url",
            ]
        cursor = MagicMock()
        cursor.description = [(col, None) for col in columns]
        cursor.fetchall.return_value = rows
        pg = MagicMock()
        pg.cursor.return_value = cursor
        return pg, cursor

    def test_returns_rows_for_corpus(self):
        row = ("doc-1", "CA", "1946-12-09", "coi_html", "html",
               "Speech text", '{"source": "CA"}', None, None)
        pg, _ = self._make_pg_with_rows([row])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        results = list(indexer.read_raw_documents_for_scope("CA"))
        assert len(results) == 1
        assert results[0]["canonical_doc_id"] == "doc-1"
        assert results[0]["extracted_text"] == "Speech text"

    def test_metadata_json_decoded_to_dict(self):
        row = ("doc-1", "LS", "2023-01-15", "internet_archive", "ia_text",
               "text", '{"proceeding_type": "debate", "sitting_number": 3}',
               "https://archive.org/...", None)
        pg, _ = self._make_pg_with_rows([row])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        results = list(indexer.read_raw_documents_for_scope("LS"))
        meta = results[0]["metadata_json"]
        assert isinstance(meta, dict)
        assert meta["proceeding_type"] == "debate"
        assert meta["sitting_number"] == 3

    def test_date_from_filter_added_to_query(self):
        pg, cursor = self._make_pg_with_rows([])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        list(indexer.read_raw_documents_for_scope("LS", date_from="2024-01-01"))
        sql = cursor.execute.call_args[0][0]
        assert "date >= %s" in sql
        params = cursor.execute.call_args[0][1]
        assert "2024-01-01" in params

    def test_date_to_filter_added_to_query(self):
        pg, cursor = self._make_pg_with_rows([])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        list(indexer.read_raw_documents_for_scope("RS", date_to="2024-12-31"))
        sql = cursor.execute.call_args[0][0]
        assert "date <= %s" in sql
        params = cursor.execute.call_args[0][1]
        assert "2024-12-31" in params

    def test_date_from_and_to_both_added(self):
        pg, cursor = self._make_pg_with_rows([])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        list(indexer.read_raw_documents_for_scope(
            "LS", date_from="2024-01-01", date_to="2024-12-31"
        ))
        sql = cursor.execute.call_args[0][0]
        assert "date >= %s" in sql
        assert "date <= %s" in sql

    def test_no_date_filter_omitted(self):
        pg, cursor = self._make_pg_with_rows([])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        list(indexer.read_raw_documents_for_scope("CA"))
        sql = cursor.execute.call_args[0][0]
        assert "date >=" not in sql
        assert "date <=" not in sql

    def test_none_metadata_json_normalised_to_empty_dict(self):
        row = ("doc-x", "CA", None, "coi_html", "html",
               None, None, None, None)
        pg, _ = self._make_pg_with_rows([row])
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        results = list(indexer.read_raw_documents_for_scope("CA"))
        assert results[0]["metadata_json"] == {}


# ── Stage 1 re-run dedup (PK guard) ──────────────────────────────────────────

class TestStage1PKDedup:
    """
    Stage 1 dedup: indexer.check_raw_document_exists() is called before writing.
    If it returns True, no write should occur.
    """

    def test_stage1_skips_already_fetched_document(self):
        """
        If check_raw_document_exists() returns True, write_raw_document must
        not be called for that document.
        """
        check_cursor = MagicMock()
        check_cursor.fetchone.return_value = (1,)  # already exists
        write_cursor = MagicMock()
        write_cursor.fetchone.return_value = None

        call_count = {"check": 0, "write": 0}
        executed_sqls = []

        def fake_cursor():
            c = MagicMock()
            def fake_execute(sql, params=None):
                executed_sqls.append(sql)
                if "SELECT 1 FROM raw_documents" in sql:
                    call_count["check"] += 1
                    c.fetchone.return_value = (1,)
                elif "INSERT INTO raw_documents" in sql:
                    call_count["write"] += 1
                    c.fetchone.return_value = None
            c.execute.side_effect = fake_execute
            c.description = [("canonical_doc_id", None)]
            c.fetchall.return_value = []
            return c

        pg = MagicMock()
        pg.cursor.side_effect = fake_cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        # Simulate Stage 1 dedup check
        exists = indexer.check_raw_document_exists("doc-already-fetched")
        assert exists is True

        # Since it exists, Stage 1 would skip; verify write not called
        # (this tests the check function itself — orchestrator tests verify skipping)
        assert call_count["check"] == 1
        assert call_count["write"] == 0


# ── CA orchestrator Stage 1/2 ────────────────────────────────────────────────

class TestCAOrchestratorStage1:
    """CA orchestrator Stage 1: writes one raw_documents row per document."""

    def _make_ca_orchestrator(self, indexer, checkpoint, doc_refs=None, content="<html>CA sitting</html>"):
        """Build a CAOrchestrator with a fully mocked provider and client."""
        from ingest.sources.ca import CAOrchestrator
        from ingest.sources._provider import DocumentRef

        if doc_refs is None:
            doc_refs = [
                DocumentRef(
                    canonical_doc_id="ca-doc-1",
                    corpus="CA",
                    provider="coi_html",
                    format="html",
                    fetch_url="https://www.constitutionofindia.net/debates/1946-12-09",
                    citation_url="https://www.constitutionofindia.net/debates/1946-12-09",
                    metadata={"volume": 1},
                )
            ]

        provider = MagicMock()
        provider.discover = AsyncMock(return_value=doc_refs)
        provider.fetch = AsyncMock(return_value=content)

        client = MagicMock()
        return CAOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            names_dict={},
            provider=provider,
        ), provider

    def test_run_stage1_writes_one_row_per_document(self, tmp_path):
        """Stage 1 writes exactly one raw_documents row per discovered document."""
        writes = []

        def fake_check(doc_id):
            return False  # not yet fetched

        def fake_write(**kwargs):
            writes.append(kwargs)

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(side_effect=fake_check)
        indexer.write_raw_document = MagicMock(side_effect=lambda **kw: writes.append(kw))

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": None, "proceeding_type": "debate",
                "raw_text": "Speech text here.", "raw_html": "<html>...</html>",
            }):
                stats = asyncio.run(orch.run_stage1())

        assert stats["fetched"] == 1
        assert stats["skipped"] == 0
        assert len(writes) == 1
        write = writes[0]
        assert write["canonical_doc_id"] == "ca-doc-1"
        assert write["corpus"] == "CA"
        assert write["format"] == "html"
        assert write["provider"] == "coi_html"

    def test_run_stage1_skips_already_fetched_document(self, tmp_path):
        """Stage 1 skips documents already in raw_documents (PK dedup)."""
        writes = []

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=True)  # already fetched
        indexer.write_raw_document = MagicMock(side_effect=lambda **kw: writes.append(kw))

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            stats = asyncio.run(orch.run_stage1())

        assert stats["skipped"] == 1
        assert stats["fetched"] == 0
        assert len(writes) == 0

    def test_run_stage1_does_not_call_mark_document_processed(self, tmp_path):
        """Stage 1 must NOT write to the SQLite processed_documents checkpoint."""
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)
        indexer.write_raw_document = MagicMock()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": "1946-12-09", "raw_text": "text",
            }):
                asyncio.run(orch.run_stage1())

            # No SQLite checkpoint entries should be written for Stage 1
            assert cp.processed_document_count() == 0

    def test_run_stage1_date_from_url_slug_set_in_metadata(self, tmp_path):
        """CA date from URL slug is stored in metadata_json before write."""
        metadata_kwarg = {}

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)

        def capture_write(**kwargs):
            metadata_kwarg.update(kwargs)

        indexer.write_raw_document = MagicMock(side_effect=capture_write)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": None, "raw_text": "Some text",
                "proceeding_type": "debate",
            }):
                asyncio.run(orch.run_stage1())

        # URL slug "1946-12-09" from fetch_url should set date in write call
        assert metadata_kwarg.get("date") == "1946-12-09"

    def test_run_stage1_excludes_raw_html_from_metadata_json(self, tmp_path):
        """raw_html must not appear in metadata_json (large field, unused by segmenters)."""
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)
        indexer.write_raw_document = MagicMock()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": "1946-12-09",
                "raw_text": "Speech text",
                "raw_html": "<html><body>Big HTML...</body></html>",
            }):
                asyncio.run(orch.run_stage1())

        call_kwargs = indexer.write_raw_document.call_args[1]
        assert "raw_html" not in call_kwargs["metadata_json"]

    def test_run_stage1_raw_text_in_extracted_text_not_metadata(self, tmp_path):
        """raw_text must be stored as extracted_text, not inside metadata_json."""
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)
        indexer.write_raw_document = MagicMock()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": "1946-12-09",
                "raw_text": "The actual speech content.",
            }):
                asyncio.run(orch.run_stage1())

        kw = indexer.write_raw_document.call_args[1]
        assert kw["extracted_text"] == "The actual speech content."
        assert "raw_text" not in kw["metadata_json"]

    def test_stage1_rerun_writes_zero_new_rows_for_fetched_corpus(self, tmp_path):
        """Stage 1 re-run against a fully fetched corpus writes zero new rows."""
        write_count = [0]

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        # Simulate: first call returns False (new), subsequent returns True (exists)
        call_counts = [0]

        def check_exists(doc_id):
            call_counts[0] += 1
            return call_counts[0] > 1  # False first time, True on re-run

        indexer.check_raw_document_exists = MagicMock(side_effect=check_exists)

        def fake_write(**kwargs):
            write_count[0] += 1

        indexer.write_raw_document = MagicMock(side_effect=fake_write)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch, _ = self._make_ca_orchestrator(indexer, cp)
            with patch("ingest.sources.ca.parse_html", return_value={
                "source": "CA", "date": "1946-12-09", "raw_text": "text",
            }):
                # First run
                s1_first = asyncio.run(orch.run_stage1())

        # Reset call counter
        call_counts[0] = 1  # second call will now return True (already fetched)
        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch2, _ = self._make_ca_orchestrator(indexer, cp)
            s1_second = asyncio.run(orch2.run_stage1())

        assert s1_first["fetched"] == 1
        assert s1_second["fetched"] == 0
        assert s1_second["skipped"] == 1


# ── CA orchestrator Stage 2 ───────────────────────────────────────────────────

class TestCAOrchestratorStage2:
    """CA orchestrator Stage 2: reads raw_documents rows and produces indexed records."""

    def _make_raw_row(self, canonical_doc_id="ca-doc-1", date="1946-12-09",
                      extracted_text="Speech text.", metadata=None):
        if metadata is None:
            metadata = {
                "source": "CA",
                "proceeding_type": "debate",
                "date": date,
                "source_url": "https://www.constitutionofindia.net/...",
                "volume": 1,
            }
        return {
            "canonical_doc_id": canonical_doc_id,
            "corpus": "CA",
            "date": date,
            "provider": "coi_html",
            "format": "html",
            "extracted_text": extracted_text,
            "metadata_json": metadata,
            "fetch_url": "https://www.constitutionofindia.net/...",
            "citation_url": "https://www.constitutionofindia.net/...",
        }

    def test_run_stage2_reads_from_raw_documents_and_indexes(self, tmp_path):
        """Stage 2 reads raw_documents rows and calls indexer.index_record."""
        from ingest.sources.ca import CAOrchestrator

        raw_row = self._make_raw_row()
        indexed_records = []

        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=[raw_row])

        def fake_index(record, checkpoint):
            indexed_records.append(record)
            return True

        indexer.index_record = MagicMock(side_effect=fake_index)

        client = MagicMock()
        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = CAOrchestrator(client, cp, indexer, {})
            with patch("ingest.sources.ca.segment_speeches") as mock_seg:
                mock_seg.return_value = [
                    {
                        "source": "CA",
                        "proceeding_type": "debate",
                        "date": "1946-12-09",
                        "full_text_en": "Speech content",
                        "speaker_name": "Ambedkar",
                        "lang_original": "en",
                        "is_translated": False,
                        "has_untranslated_content": False,
                    }
                ]
                stats = asyncio.run(orch.run_stage2())

        assert stats["indexed"] == 1
        assert len(indexed_records) == 1
        assert indexed_records[0]["record_type"] == "speech"

    def test_run_stage2_skips_already_processed_documents(self, tmp_path):
        """Stage 2 respects SQLite processed_documents checkpoint for resumability."""
        from ingest.sources.ca import CAOrchestrator

        raw_row = self._make_raw_row()

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=[raw_row])
        indexer.index_record = MagicMock(return_value=True)

        client = MagicMock()
        with CheckpointStore(tmp_path / "cp.db") as cp:
            # Mark the document as already processed (simulates prior Stage 2 run)
            cp.mark_document_processed("ca-doc-1", corpus="CA")
            orch = CAOrchestrator(client, cp, indexer, {})
            with patch("ingest.sources.ca.segment_speeches", return_value=[]):
                stats = asyncio.run(orch.run_stage2())

        assert stats["skipped"] == 1
        assert stats["indexed"] == 0
        indexer.index_record.assert_not_called()

    def test_run_stage2_marks_document_processed_after_indexing(self, tmp_path):
        """Stage 2 writes processed_documents entry after all records are indexed."""
        from ingest.sources.ca import CAOrchestrator

        raw_row = self._make_raw_row()

        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=[raw_row])
        indexer.index_record = MagicMock(return_value=True)

        client = MagicMock()
        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = CAOrchestrator(client, cp, indexer, {})
            with patch("ingest.sources.ca.segment_speeches") as mock_seg:
                mock_seg.return_value = [{"source": "CA", "proceeding_type": "debate",
                                           "date": "1946-12-09", "lang_original": "en",
                                           "is_translated": False, "has_untranslated_content": False}]
                asyncio.run(orch.run_stage2())
            # After Stage 2, the SQLite checkpoint must record the document
            assert cp.is_document_processed("ca-doc-1") is True

    def test_run_stage2_date_from_passed_to_read_scope(self, tmp_path):
        """--date-from is forwarded to read_raw_documents_for_scope."""
        from ingest.sources.ca import CAOrchestrator

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=[])

        client = MagicMock()
        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = CAOrchestrator(client, cp, indexer, {})
            asyncio.run(orch.run_stage2(date_from="2024-01-01", date_to="2024-12-31"))

        indexer.read_raw_documents_for_scope.assert_called_once_with(
            "CA", "2024-01-01", "2024-12-31"
        )

    def test_run_stage2_reconstructs_raw_record_from_metadata_and_text(self, tmp_path):
        """
        Stage 2 reconstructs raw_record = {**metadata_json, 'raw_text': extracted_text}
        and passes it to segment_speeches.
        """
        from ingest.sources.ca import CAOrchestrator

        raw_row = self._make_raw_row(
            extracted_text="Speech content from DB.",
            metadata={"source": "CA", "date": "1946-12-09",
                      "proceeding_type": "debate", "volume": 2, "ca_speech_pairs": None},
        )

        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=[raw_row])
        indexer.index_record = MagicMock(return_value=True)

        segmenter_inputs = []
        client = MagicMock()
        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = CAOrchestrator(client, cp, indexer, {})
            with patch("ingest.sources.ca.segment_speeches") as mock_seg:
                def capture(raw_record, source):
                    segmenter_inputs.append(dict(raw_record))
                    return []
                mock_seg.side_effect = capture
                asyncio.run(orch.run_stage2())

        assert len(segmenter_inputs) == 1
        r = segmenter_inputs[0]
        assert r["raw_text"] == "Speech content from DB."
        assert r["source"] == "CA"
        assert r["date"] == "1946-12-09"


# ── Stage 2 resumability ──────────────────────────────────────────────────────

class TestStage2Resumability:
    """Stage 2 resumes from SQLite checkpoint after interruption."""

    def test_interrupted_stage2_resumes_from_checkpoint(self, tmp_path):
        """
        After an interrupted Stage 2 run (docs 0-1 processed), resuming must
        only process the remaining docs (doc 2 onwards).
        """
        from ingest.sources.ca import CAOrchestrator

        rows = [
            {
                "canonical_doc_id": f"ca-doc-{i}",
                "corpus": "CA", "date": f"194{i}-01-01",
                "provider": "coi_html", "format": "html",
                "extracted_text": f"text {i}",
                "metadata_json": {"source": "CA", "date": f"194{i}-01-01",
                                  "proceeding_type": "debate"},
                "fetch_url": None, "citation_url": None,
            }
            for i in range(3)
        ]

        pg = _make_mock_pg_conn(inserted=True)
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.read_raw_documents_for_scope = MagicMock(return_value=rows)
        indexer.index_record = MagicMock(return_value=True)

        client = MagicMock()

        # First partial run: process only the first 2 docs
        with CheckpointStore(tmp_path / "cp.db") as cp:
            cp.mark_document_processed("ca-doc-0", corpus="CA")
            cp.mark_document_processed("ca-doc-1", corpus="CA")

            orch = CAOrchestrator(client, cp, indexer, {})
            with patch("ingest.sources.ca.segment_speeches") as mock_seg:
                mock_seg.return_value = [{"source": "CA", "proceeding_type": "debate",
                                           "date": "1946-01-01", "lang_original": "en",
                                           "is_translated": False, "has_untranslated_content": False}]
                stats = asyncio.run(orch.run_stage2())

        # Only ca-doc-2 should be processed (the other two were already checkpointed)
        assert stats["skipped"] == 2
        assert stats["indexed"] == 1


# ── main.py argument parsing ──────────────────────────────────────────────────

class TestMainArgParsing:
    def test_stage_defaults_to_all(self):
        args = main_mod._parse_args(["--source", "ca"])
        assert args.stage == "all"

    def test_stage_fetch_accepted(self):
        args = main_mod._parse_args(["--source", "ca", "--stage", "fetch"])
        assert args.stage == "fetch"

    def test_stage_process_accepted(self):
        args = main_mod._parse_args(["--source", "ls", "--stage", "process"])
        assert args.stage == "process"

    def test_stage_all_accepted(self):
        args = main_mod._parse_args(["--source", "rs", "--stage", "all"])
        assert args.stage == "all"

    def test_invalid_stage_rejected(self):
        with pytest.raises(SystemExit):
            main_mod._parse_args(["--source", "ca", "--stage", "invalid"])

    def test_date_from_parsed(self):
        args = main_mod._parse_args(["--source", "ls", "--date-from", "2024-01-01"])
        assert args.date_from == "2024-01-01"

    def test_date_to_parsed(self):
        args = main_mod._parse_args(["--source", "rs", "--date-to", "2024-12-31"])
        assert args.date_to == "2024-12-31"

    def test_date_override_removed(self):
        """--date-override must no longer be a valid argument."""
        with pytest.raises(SystemExit):
            main_mod._parse_args(["--source", "ls", "--date-override", "2014-01-01"])

    def test_date_from_defaults_to_none(self):
        args = main_mod._parse_args(["--source", "ca"])
        assert args.date_from is None

    def test_date_to_defaults_to_none(self):
        args = main_mod._parse_args(["--source", "ca"])
        assert args.date_to is None


# ── main.py orchestrator construction ────────────────────────────────────────

class TestMakeOrchestrator:
    def _commons(self):
        return MagicMock(name="client"), MagicMock(name="checkpoint"), \
            MagicMock(name="indexer"), {}

    def test_ca_builds_ca_orchestrator(self):
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "CAOrchestrator") as ca_cls:
            main_mod._make_orchestrator("ca", client, checkpoint, indexer, names)
        ca_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_ls_builds_ls_orchestrator(self):
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "LSOrchestrator") as ls_cls:
            main_mod._make_orchestrator("ls", client, checkpoint, indexer, names)
        ls_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_rs_builds_rs_orchestrator(self):
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "RSOrchestrator") as rs_cls:
            main_mod._make_orchestrator("rs", client, checkpoint, indexer, names)
        rs_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_unknown_source_raises(self):
        client, checkpoint, indexer, names = self._commons()
        with pytest.raises(ValueError):
            main_mod._make_orchestrator("xx", client, checkpoint, indexer, names)


# ── main.py stage routing ─────────────────────────────────────────────────────

def _make_stage_mock():
    """Return a mock orchestrator class with async run_stage1/run_stage2/run methods."""
    s1_stats = {"fetched": 2, "skipped": 0, "errors": 0}
    s2_stats = {"indexed": 5, "skipped": 0, "errors": 0}
    run_stats = {"indexed": 5, "skipped": 0, "errors": 0}
    instance = MagicMock()
    instance.run_stage1 = AsyncMock(return_value=s1_stats)
    instance.run_stage2 = AsyncMock(return_value=s2_stats)
    instance.run = AsyncMock(return_value=run_stats)
    cls = MagicMock(return_value=instance)
    return cls


def _patched_stage_main(
    argv: list[str],
    ca_cls: Any,
    ls_cls: Any,
    rs_cls: Any,
    indexer_inst: Any = None,
) -> int:
    if indexer_inst is None:
        indexer_inst = MagicMock()
        indexer_inst.counts = {"CA": 0, "LS": 0, "RS": 0}

    checkpoint_inst = MagicMock()
    checkpoint_inst.__enter__ = MagicMock(return_value=checkpoint_inst)
    checkpoint_inst.__exit__ = MagicMock(return_value=False)

    with patch.object(main_mod, "_connect_postgres", return_value=MagicMock()), \
         patch.object(main_mod, "_connect_meilisearch", return_value=MagicMock()), \
         patch.object(main_mod, "load_names_dict", return_value={}), \
         patch.object(main_mod, "Indexer", return_value=indexer_inst), \
         patch.object(main_mod, "CheckpointStore", return_value=checkpoint_inst), \
         patch.object(main_mod, "CAOrchestrator", ca_cls), \
         patch.object(main_mod, "LSOrchestrator", ls_cls), \
         patch.object(main_mod, "RSOrchestrator", rs_cls):
        return main_mod.main(argv)


class TestMainStageRouting:
    def test_stage_fetch_calls_run_stage1_only(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        rc = _patched_stage_main(["--source", "ca", "--stage", "fetch"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run_stage1.assert_awaited_once()
        ca_cls.return_value.run_stage2.assert_not_called()
        ca_cls.return_value.run.assert_not_called()

    def test_stage_process_calls_run_stage2_only(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        rc = _patched_stage_main(["--source", "ls", "--stage", "process"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ls_cls.return_value.run_stage2.assert_awaited_once()
        ls_cls.return_value.run_stage1.assert_not_called()
        ls_cls.return_value.run.assert_not_called()

    def test_stage_all_calls_both_stage1_and_stage2(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        rc = _patched_stage_main(["--source", "rs", "--stage", "all"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        rs_cls.return_value.run_stage1.assert_awaited_once()
        rs_cls.return_value.run_stage2.assert_awaited_once()

    def test_stage_all_is_default(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        rc = _patched_stage_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run_stage1.assert_awaited_once()
        ca_cls.return_value.run_stage2.assert_awaited_once()

    def test_stage_process_date_from_passed_to_run_stage2(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        _patched_stage_main(
            ["--source", "ca", "--stage", "process", "--date-from", "2024-01-01"],
            ca_cls, ls_cls, rs_cls,
        )
        ca_cls.return_value.run_stage2.assert_awaited_once_with(
            date_from="2024-01-01", date_to=None
        )

    def test_stage_process_date_to_passed_to_run_stage2(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        _patched_stage_main(
            ["--source", "ca", "--stage", "process",
             "--date-from", "2024-01-01", "--date-to", "2024-12-31"],
            ca_cls, ls_cls, rs_cls,
        )
        ca_cls.return_value.run_stage2.assert_awaited_once_with(
            date_from="2024-01-01", date_to="2024-12-31"
        )

    def test_date_from_passed_to_run_stage1(self):
        """--date-from is forwarded to run_stage1 (both-stage scope fix)."""
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        _patched_stage_main(
            ["--source", "ca", "--stage", "all", "--date-from", "2024-01-01"],
            ca_cls, ls_cls, rs_cls,
        )
        ca_cls.return_value.run_stage1.assert_awaited_once_with(
            date_from="2024-01-01", date_to=None
        )

    def test_source_all_runs_all_three_in_order(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        _patched_stage_main(["--source", "all", "--stage", "fetch"], ca_cls, ls_cls, rs_cls)
        ca_cls.return_value.run_stage1.assert_awaited_once()
        ls_cls.return_value.run_stage1.assert_awaited_once()
        rs_cls.return_value.run_stage1.assert_awaited_once()

    def test_stage_process_calls_update_index_status(self):
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        indexer_inst = MagicMock()
        indexer_inst.counts = {"CA": 0, "LS": 0, "RS": 0}
        _patched_stage_main(["--source", "ca", "--stage", "process"],
                            ca_cls, ls_cls, rs_cls, indexer_inst=indexer_inst)
        indexer_inst.update_index_status.assert_called_once()

    def test_stage_fetch_does_not_call_update_index_status(self):
        """index_status is only updated after Stage 2, not after Stage 1."""
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        indexer_inst = MagicMock()
        indexer_inst.counts = {"CA": 0, "LS": 0, "RS": 0}
        _patched_stage_main(["--source", "ca", "--stage", "fetch"],
                            ca_cls, ls_cls, rs_cls, indexer_inst=indexer_inst)
        indexer_inst.update_index_status.assert_not_called()


# ── Completion summary logging ────────────────────────────────────────────────

class TestMainCompletionSummary:
    def test_stage1_summary_logged(self, caplog):
        import logging
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        with caplog.at_level(logging.INFO, logger="ingest.main"):
            _patched_stage_main(["--source", "ca", "--stage", "fetch"], ca_cls, ls_cls, rs_cls)
        messages = [r.getMessage() for r in caplog.records]
        assert any("Stage 1" in m or "fetch" in m.lower() for m in messages)

    def test_stage2_summary_logged(self, caplog):
        import logging
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        with caplog.at_level(logging.INFO, logger="ingest.main"):
            _patched_stage_main(["--source", "ca", "--stage", "process"], ca_cls, ls_cls, rs_cls)
        messages = [r.getMessage() for r in caplog.records]
        assert any("Stage 2" in m or "process" in m.lower() for m in messages)

    def test_ingestion_complete_always_logged(self, caplog):
        import logging
        ca_cls, ls_cls, rs_cls = _make_stage_mock(), _make_stage_mock(), _make_stage_mock()
        with caplog.at_level(logging.INFO, logger="ingest.main"):
            _patched_stage_main(["--source", "all"], ca_cls, ls_cls, rs_cls)
        messages = [r.getMessage() for r in caplog.records]
        assert any("Ingestion complete" in m for m in messages)


# ── date range scope: only matching rows produced ─────────────────────────────

class TestDateScopeFiltering:
    """read_raw_documents_for_scope correctly filters by date when range given."""

    def test_date_from_excludes_earlier_rows(self):
        """
        Rows with dates before date_from must not appear in the query result.
        The SQL WHERE clause is the contract — we verify the clause is present.
        """
        cursor = MagicMock()
        cursor.description = [
            ("canonical_doc_id", None), ("corpus", None), ("date", None),
            ("provider", None), ("format", None), ("extracted_text", None),
            ("metadata_json", None), ("fetch_url", None), ("citation_url", None),
        ]
        cursor.fetchall.return_value = []
        pg = MagicMock()
        pg.cursor.return_value = cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)

        list(indexer.read_raw_documents_for_scope("LS", date_from="2024-01-01", date_to="2024-12-31"))

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]

        assert "corpus = %s" in sql
        assert "date >= %s" in sql
        assert "date <= %s" in sql
        assert "LS" in params
        assert "2024-01-01" in params
        assert "2024-12-31" in params


# ── LS and RS orchestrators have run_stage1 / run_stage2 ─────────────────────

class TestLSRSOrchestratorStageMethods:
    """Verify LS and RS orchestrators expose the same Stage 1/2 interface as CA."""

    def test_ls_orchestrator_has_run_stage1(self):
        from ingest.sources.ls import LSOrchestrator
        assert hasattr(LSOrchestrator, "run_stage1")

    def test_ls_orchestrator_has_run_stage2(self):
        from ingest.sources.ls import LSOrchestrator
        assert hasattr(LSOrchestrator, "run_stage2")

    def test_rs_orchestrator_has_run_stage1(self):
        from ingest.sources.rs import RSOrchestrator
        assert hasattr(RSOrchestrator, "run_stage1")

    def test_rs_orchestrator_has_run_stage2(self):
        from ingest.sources.rs import RSOrchestrator
        assert hasattr(RSOrchestrator, "run_stage2")

    def test_ca_orchestrator_has_run(self):
        from ingest.sources.ca import CAOrchestrator
        assert hasattr(CAOrchestrator, "run")

    def test_ls_stage1_does_not_call_mark_document_processed(self, tmp_path):
        """LS Stage 1 must not write to the SQLite checkpoint."""
        from ingest.sources.ls import LSOrchestrator
        from ingest.sources._provider import DocumentRef

        doc_ref = DocumentRef(
            canonical_doc_id="12345",
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/...",
            citation_url="https://eparlib.sansad.in/...",
            metadata={},
        )
        provider = MagicMock()
        provider.discover = AsyncMock(return_value=[doc_ref])
        provider.fetch = AsyncMock(return_value="IA text content")

        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)
        indexer.write_raw_document = MagicMock()

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = LSOrchestrator(
                MagicMock(), cp, indexer, {}, providers=[provider]
            )
            with patch("ingest.sources.ls.parse_ia_text", return_value={
                "source": "LS", "date": "2023-01-15", "raw_text": "IA text content",
                "proceeding_type": "debate",
            }):
                asyncio.run(orch.run_stage1())
            assert cp.processed_document_count() == 0

    def test_rs_stage1_applies_citation_url_override_before_write(self, tmp_path):
        """RS Stage 1 applies the canonical citation rule before writing to raw_documents."""
        from ingest.sources.rs import RSOrchestrator
        from ingest.sources._provider import DocumentRef

        doc_ref = DocumentRef(
            canonical_doc_id="rs-67890",
            corpus="RS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/...",
            citation_url="https://rsdebate.nic.in/handle/123456789/67890",
            metadata={},
        )
        provider = MagicMock()
        provider.discover = AsyncMock(return_value=[doc_ref])
        provider.fetch = AsyncMock(return_value="RS IA text")

        write_kwargs = {}
        pg = _make_mock_pg_conn()
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        indexer.check_raw_document_exists = MagicMock(return_value=False)

        def capture(**kw):
            write_kwargs.update(kw)

        indexer.write_raw_document = MagicMock(side_effect=capture)

        with CheckpointStore(tmp_path / "cp.db") as cp:
            orch = RSOrchestrator(
                MagicMock(), cp, indexer, {}, providers=[provider]
            )
            with patch("ingest.sources.rs.parse_ia_text", return_value={
                "source": "RS", "date": "2023-03-10", "raw_text": "RS text",
                "proceeding_type": "debate",
                "source_url": "https://rsdebate.nic.in/handle/123456789/67890",
            }):
                asyncio.run(orch.run_stage1())

        # citation_url passed to write must be the rsdebate URL (not archive.org)
        assert write_kwargs.get("citation_url") == "https://rsdebate.nic.in/handle/123456789/67890"
        # metadata_json["source_url"] must also be the canonical URL
        assert write_kwargs["metadata_json"].get("source_url") == "https://rsdebate.nic.in/handle/123456789/67890"
