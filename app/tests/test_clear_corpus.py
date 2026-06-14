"""Tests for scripts/clear_corpus.py — the --target checkpoints rename and the
PostgreSQL checkpoint clear (DEPLOYMENT §6.5 / §7 task 3).

The checkpoint clear is now a PostgreSQL DELETE (no SQLite). These tests mock the
PostgreSQL connection and assert the SQL issued; no live database is required.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "clear_corpus.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("clear_corpus", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


clear_corpus = _load_module()


class _RecordingCursor:
    """Captures (sql, params) for every execute; supports the `with conn.cursor()` form."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return (0,)

    @property
    def rowcount(self):
        return 0


def _fake_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ── argparse: --target rename ─────────────────────────────────────────────────


class TestArgparseTargetRename:
    def test_target_sqlite_is_rejected(self, monkeypatch):
        """The old --target sqlite is no longer a valid choice."""
        monkeypatch.setattr(
            "sys.argv", ["clear_corpus.py", "--corpus", "ls", "--target", "sqlite"]
        )
        with pytest.raises(SystemExit):
            clear_corpus.main()

    def test_target_checkpoints_is_accepted(self, monkeypatch):
        """--target checkpoints parses and routes to the checkpoints clear only."""
        monkeypatch.setattr(
            "sys.argv",
            ["clear_corpus.py", "--corpus", "ls", "--target", "checkpoints", "--dry-run"],
        )
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.main()
        # A checkpoints clear touched processed_documents; Meilisearch was not touched.
        assert any("processed_documents" in sql for sql, _ in cursor.calls)


# ── checkpoint clear issues PostgreSQL DELETEs ────────────────────────────────


class TestClearCheckpoints:
    def test_target_checkpoints_deletes_both_tables(self):
        """--target checkpoints (no date scope) DELETEs both checkpoint tables in PG."""
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.run(
                corpus="LS", stage=None, targets=["checkpoints"],
                date_from=None, date_to=None, dry_run=False,
            )
        deletes = [sql for sql, _ in cursor.calls if sql.strip().upper().startswith("DELETE")]
        assert any("DELETE FROM processed_documents" in s for s in deletes)
        assert any("DELETE FROM ingestion_dedup_keys" in s for s in deletes)

    def test_stage_process_clears_processed_documents_only(self):
        """--stage process clears processed_documents but NOT ingestion_dedup_keys."""
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.clear_checkpoints(
                "LS", None, None, dry_run=False, include_dedup_keys=False
            )
        deletes = [sql for sql, _ in cursor.calls if sql.strip().upper().startswith("DELETE")]
        assert any("DELETE FROM processed_documents" in s for s in deletes)
        assert not any("ingestion_dedup_keys" in s for s in deletes)

    def test_stage_fetch_clears_both_checkpoint_tables(self):
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.clear_checkpoints(
                "LS", None, None, dry_run=False, include_dedup_keys=True
            )
        deletes = [sql for sql, _ in cursor.calls if sql.strip().upper().startswith("DELETE")]
        assert any("DELETE FROM processed_documents" in s for s in deletes)
        assert any("DELETE FROM ingestion_dedup_keys" in s for s in deletes)

    def test_date_scoped_uses_raw_documents_join_and_skips_dedup_keys(self):
        """A date-scoped checkpoint clear joins raw_documents and never touches the mirror."""
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.clear_checkpoints(
                "LS", "2024-01-01", "2024-12-31",
                dry_run=False, include_dedup_keys=True,  # requested, but date-scoped → skipped
            )
        deletes = [sql for sql, _ in cursor.calls if sql.strip().upper().startswith("DELETE")]
        pd_delete = next(s for s in deletes if "processed_documents" in s)
        assert "USING raw_documents" in pd_delete
        assert not any("ingestion_dedup_keys" in s for s in deletes)

    def test_dry_run_issues_no_delete(self):
        cursor = _RecordingCursor()
        with patch.object(clear_corpus, "_pg_connect", return_value=_fake_conn(cursor)):
            clear_corpus.clear_checkpoints(
                "LS", None, None, dry_run=True, include_dedup_keys=True
            )
        assert not any(
            sql.strip().upper().startswith("DELETE") for sql, _ in cursor.calls
        )
        assert any("SELECT COUNT(*)" in sql for sql, _ in cursor.calls)
