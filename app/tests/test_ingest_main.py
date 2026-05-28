"""Tests for ingest.main — CLI argument parsing and pipeline orchestration."""
from __future__ import annotations

import argparse
import logging
import pytest
from datetime import date as date_type
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ingest.main import (
    _async_main,
    _canonicalize_record,
    _parse_args,
    _process_document,
    _run_source,
)


# ── CLI argument parsing ───────────────────────────────────────────────────────

class TestParseArgs:
    def test_source_ca(self):
        args = _parse_args(["--source", "ca"])
        assert args.source == "ca"

    def test_source_all(self):
        args = _parse_args(["--source", "all"])
        assert args.source == "all"

    def test_date_override(self):
        args = _parse_args(["--source", "ls", "--date-override", "2020-01-01"])
        assert args.date_override == "2020-01-01"

    def test_reindex_from_db_flag(self):
        args = _parse_args(["--source", "all", "--reindex-from-db"])
        assert args.reindex_from_db is True

    def test_reindex_from_db_default_false(self):
        args = _parse_args(["--source", "ca"])
        assert args.reindex_from_db is False

    def test_missing_source_raises(self):
        with pytest.raises(SystemExit):
            _parse_args([])

    @pytest.mark.parametrize("source", ["ca", "ls", "rs", "all"])
    def test_all_valid_source_values_accepted(self, source):
        """All four valid --source values must be accepted without error."""
        args = _parse_args(["--source", source])
        assert args.source == source

    def test_invalid_source_raises(self):
        """An unrecognised --source value must cause argparse to exit."""
        with pytest.raises(SystemExit):
            _parse_args(["--source", "foo"])


# ── _canonicalize_record ───────────────────────────────────────────────────────

class TestCanonicalizeRecord:
    def test_strips_honorific_from_speaker_name(self):
        names_dict = {"narendra modi": "Narendra Modi"}
        record = {
            "source": "LS",
            "speaker_name": "Shri Narendra Modi",
            "session_name": "Budget Session 2023",
        }
        result = _canonicalize_record(record, names_dict)
        assert result["speaker_name"] == "Narendra Modi"
        assert result["speaker_name_unresolved"] is False

    def test_unresolved_name_sets_flag(self):
        names_dict = {}
        record = {
            "source": "LS",
            "speaker_name": "Unknown Person",
            "session_name": "Budget Session 2023",
        }
        result = _canonicalize_record(record, names_dict)
        assert result["speaker_name_unresolved"] is True
        assert result["speaker_name"] == "Unknown Person"

    def test_session_name_canonicalized(self):
        names_dict = {}
        record = {
            "source": "LS",
            "speaker_name": "Test Member",
            "session_name": "Budget Session, 2023",
        }
        result = _canonicalize_record(record, names_dict)
        assert result["session_name"] == "Budget Session 2023"

    def test_ca_session_name_set_to_none(self):
        names_dict = {}
        record = {
            "source": "CA",
            "speaker_name": "Dr. B. R. Ambedkar",
            "session_name": "Constituent Assembly Debate",
        }
        result = _canonicalize_record(record, names_dict)
        assert result["session_name"] is None

    def test_none_speaker_name_unchanged(self):
        names_dict = {}
        record = {
            "source": "LS",
            "speaker_name": None,
            "session_name": None,
        }
        result = _canonicalize_record(record, names_dict)
        assert result["speaker_name"] is None
        assert result["speaker_name_unresolved"] is False


# ── _process_document ─────────────────────────────────────────────────────────

class TestProcessDocument:
    @pytest.mark.asyncio
    async def test_skips_document_with_no_date(self, tmp_path):
        """Document with no parseable date must be skipped and count as an error."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        pg = MagicMock()
        meili = MagicMock()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}
        names_dict = {}

        # HTML that has no date
        html_no_date = "<html><body><p>No date here.</p></body></html>"
        with CheckpointStore(tmp_path / "cp.db") as cp:
            await _process_document(
                url="http://example.com/no_date.html",
                content=html_no_date,
                meta={"source": "LS", "proceeding_type_hint": "debate"},
                indexer=indexer,
                checkpoint=cp,
                names_dict=names_dict,
                stats=stats,
            )

        assert stats["errors"] == 1
        assert stats["indexed"] == 0

    @pytest.mark.asyncio
    async def test_processes_html_speech_document(self, tmp_path):
        """A valid HTML debate document is parsed, segmented, and indexed."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        # Minimal debate HTML with a date and a speech
        html = """<html>
        <h1>Lok Sabha Debates — 15 March 2023</h1>
        <body>
        <p>SHRI NARENDRA MODI :</p>
        <p>The government has taken major infrastructure steps.</p>
        </body></html>"""

        pg_cursor = MagicMock()
        pg_cursor.fetchone.return_value = ("uuid-1",)
        pg = MagicMock()
        pg.cursor.return_value = pg_cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}
        names_dict = {}

        with CheckpointStore(tmp_path / "cp.db") as cp:
            await _process_document(
                url="https://sansad.in/ls/2023/03/15/debate.html",
                content=html,
                meta={"source": "LS", "proceeding_type_hint": "debate"},
                indexer=indexer,
                checkpoint=cp,
                names_dict=names_dict,
                stats=stats,
            )

        assert stats["errors"] == 0
        assert stats["documents"] == 1
        assert stats["indexed"] >= 1, (
            "A valid speech document must produce at least one indexed record"
        )


# ── Missing date logging ──────────────────────────────────────────────────────

class TestMissingDateLogging:
    @pytest.mark.asyncio
    async def test_missing_date_produces_exactly_one_error_log(self, tmp_path, caplog):
        """A document with no date produces exactly one error log entry."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        pg = MagicMock()
        meili = MagicMock()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}

        html_no_date = "<html><body><p>No date anywhere.</p></body></html>"

        with caplog.at_level(logging.ERROR, logger="ingest.main"):
            with CheckpointStore(tmp_path / "cp.db") as cp:
                await _process_document(
                    url="http://example.com/nodatehtml",
                    content=html_no_date,
                    meta={"source": "LS"},
                    indexer=indexer,
                    checkpoint=cp,
                    names_dict={},
                    stats=stats,
                )

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert any(
            "http://example.com/nodatehtml" in r.getMessage() for r in error_records
        ), "Error log must include the source URL for the skipped document"


# ── Progress logging ──────────────────────────────────────────────────────────

class TestProgressLogging:
    @pytest.mark.asyncio
    async def test_indexed_record_produces_info_log(self, tmp_path, caplog):
        """Each indexed record produces at least one INFO log entry (real-time progress)."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        html = """<html>
        <h1>Debate — 15 March 2023</h1>
        <body>
        <p>SHRI TEST MEMBER :</p>
        <p>Some speech content here for testing purposes.</p>
        </body></html>"""

        pg_cursor = MagicMock()
        pg_cursor.fetchone.return_value = ("uuid-1",)
        pg = MagicMock()
        pg.cursor.return_value = pg_cursor
        meili, _ = _make_mock_meili()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}

        with caplog.at_level(logging.INFO, logger="ingest.main"):
            with CheckpointStore(tmp_path / "cp.db") as cp:
                await _process_document(
                    url="https://sansad.in/ls/2023/03/15/debate.html",
                    content=html,
                    meta={"source": "LS", "proceeding_type_hint": "debate"},
                    indexer=indexer,
                    checkpoint=cp,
                    names_dict={},
                    stats=stats,
                )

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(info_records) >= 1
        url = "https://sansad.in/ls/2023/03/15/debate.html"
        assert any(
            url in r.getMessage() or "indexed" in r.getMessage().lower()
            for r in info_records
        ), (
            "At least one INFO log must reference the document URL or the word 'indexed' "
            "to constitute meaningful real-time progress reporting"
        )


# ── --date-override propagation ────────────────────────────────────────────────

class TestDateOverride:
    @pytest.mark.asyncio
    async def test_date_override_propagates_to_ls_source(self, tmp_path):
        """--date-override value must be forwarded to LSSource as date_from."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        pg = MagicMock()
        pg.cursor.return_value = MagicMock()
        meili = MagicMock()
        meili.index.return_value = MagicMock()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}
        override = date_type(2020, 6, 1)
        ls_init_kwargs: dict = {}

        class _MockLSSource:
            def __init__(self, **kw):
                ls_init_kwargs.update(kw)

            async def fetch_documents(self, client):
                if False:  # pragma: no cover
                    yield  # empty async generator

        with patch("ingest.main.LSSource", _MockLSSource):
            with CheckpointStore(tmp_path / "cp.db") as cp:
                await _run_source("ls", indexer, cp, {}, stats, date_override=override)

        assert ls_init_kwargs.get("date_from") == override, (
            f"LSSource must receive date_from={override!r}, got {ls_init_kwargs}"
        )

    @pytest.mark.asyncio
    async def test_date_override_propagates_to_rs_source(self, tmp_path):
        """--date-override value must be forwarded to RSSource as date_from."""
        from ingest.checkpoints.store import CheckpointStore
        from ingest.indexer import Indexer

        pg = MagicMock()
        pg.cursor.return_value = MagicMock()
        meili = MagicMock()
        meili.index.return_value = MagicMock()
        indexer = Indexer(pg, meili)
        stats = {"documents": 0, "indexed": 0, "skipped": 0, "errors": 0}
        override = date_type(2020, 6, 1)
        rs_init_kwargs: dict = {}

        class _MockRSSource:
            def __init__(self, **kw):
                rs_init_kwargs.update(kw)

            async def fetch_documents(self, client):
                if False:  # pragma: no cover
                    yield  # empty async generator

        with patch("ingest.main.RSSource", _MockRSSource):
            with CheckpointStore(tmp_path / "cp.db") as cp:
                await _run_source("rs", indexer, cp, {}, stats, date_override=override)

        assert rs_init_kwargs.get("date_from") == override, (
            f"RSSource must receive date_from={override!r}, got {rs_init_kwargs}"
        )


# ── Completion summary ─────────────────────────────────────────────────────────

class TestCompletionSummary:
    @pytest.mark.asyncio
    async def test_completion_summary_emitted(self, tmp_path, caplog):
        """
        After a normal ingestion run completes, the pipeline must emit a summary
        containing per-source totals, error count, and skipped count.
        """
        args = _parse_args(["--source", "ca"])
        pg = MagicMock()
        pg.cursor.return_value = MagicMock()
        meili, _ = _make_mock_meili()

        with patch("ingest.main._connect_postgres", return_value=pg), \
             patch("ingest.main._connect_meilisearch", return_value=meili), \
             patch("ingest.main.load_names_dict", return_value={}), \
             patch("ingest.main.CHECKPOINT_DB", tmp_path / "cp.db"), \
             patch("ingest.main._run_source", new_callable=AsyncMock), \
             caplog.at_level(logging.INFO, logger="ingest.main"):

            await _async_main(args)

        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert any("Ingestion complete" in m for m in messages), \
            "Completion banner ('=== Ingestion complete ===') must be logged"
        assert any("Total indexed" in m for m in messages), \
            "Per-source indexed totals must be logged"
        assert any("Errors" in m for m in messages), \
            "Error count must be included in the completion summary"

    @pytest.mark.asyncio
    async def test_completion_summary_counts_match_indexed(self, tmp_path, caplog):
        """
        The total count in the completion summary log must equal the sum of
        indexer.counts values after all sources have run.
        """
        args = _parse_args(["--source", "ca"])
        pg = MagicMock()
        pg.cursor.return_value = MagicMock()
        meili, _ = _make_mock_meili()

        captured: dict = {}

        async def fake_run_source(
            source_name, indexer, checkpoint, names_dict, stats, date_override=None
        ):
            # Simulate indexing 7 CA records
            indexer.counts["CA"] = 7
            stats["documents"] = 4
            captured["indexer"] = indexer

        with patch("ingest.main._connect_postgres", return_value=pg), \
             patch("ingest.main._connect_meilisearch", return_value=meili), \
             patch("ingest.main.load_names_dict", return_value={}), \
             patch("ingest.main.CHECKPOINT_DB", tmp_path / "cp.db"), \
             patch("ingest.main._run_source", new_callable=AsyncMock) as mock_rs, \
             caplog.at_level(logging.INFO, logger="ingest.main"):

            mock_rs.side_effect = fake_run_source
            await _async_main(args)

        indexer = captured["indexer"]
        total = sum(indexer.counts.values())  # 7

        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        total_lines = [m for m in messages if "Total indexed" in m]
        assert len(total_lines) >= 1, "Summary must include a 'Total indexed' line"
        assert str(total) in total_lines[0], (
            f"Summary must report total={total} but got: {total_lines[0]!r}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_meili():
    meili = MagicMock()
    index = MagicMock()
    meili.index.return_value = index
    return meili, index
