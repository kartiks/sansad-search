"""Tests for ingest.checkpoints.store — SQLite-backed checkpoint store."""
from __future__ import annotations

import pytest
from pathlib import Path

from ingest.checkpoints.store import CheckpointStore


@pytest.fixture()
def store(tmp_path):
    db_path = tmp_path / "checkpoints.db"
    with CheckpointStore(db_path) as s:
        yield s


class TestUrlTracking:
    def test_url_not_processed_initially(self, store):
        assert store.is_url_processed("http://example.com/doc.html") is False

    def test_url_processed_after_mark(self, store):
        url = "http://example.com/doc.html"
        store.mark_url_processed(url)
        assert store.is_url_processed(url) is True

    def test_other_url_not_affected(self, store):
        store.mark_url_processed("http://example.com/doc1.html")
        assert store.is_url_processed("http://example.com/doc2.html") is False

    def test_processed_url_count(self, store):
        store.mark_url_processed("http://example.com/a.html")
        store.mark_url_processed("http://example.com/b.html")
        assert store.processed_url_count() == 2

    def test_mark_url_idempotent(self, store):
        url = "http://example.com/doc.html"
        store.mark_url_processed(url)
        store.mark_url_processed(url)  # second call should not raise
        assert store.processed_url_count() == 1


class TestDedupKeyTracking:
    def test_key_absent_initially(self, store):
        assert store.has_dedup_key("LS_2023-03-15_5_debate_narendra_modi_3") is False

    def test_key_present_after_add(self, store):
        key = "LS_2023-03-15_5_debate_narendra_modi_3"
        store.add_dedup_key(key)
        assert store.has_dedup_key(key) is True

    def test_other_key_not_affected(self, store):
        store.add_dedup_key("key_one")
        assert store.has_dedup_key("key_two") is False

    def test_add_key_idempotent(self, store):
        key = "some_dedup_key"
        store.add_dedup_key(key)
        store.add_dedup_key(key)  # should not raise
        assert store.dedup_key_count() == 1

    def test_dedup_key_count(self, store):
        store.add_dedup_key("key_a")
        store.add_dedup_key("key_b")
        assert store.dedup_key_count() == 2


class TestResumability:
    def test_store_persists_across_open_close(self, tmp_path):
        """Data written in one session is available after close/re-open."""
        db_path = tmp_path / "checkpoints.db"
        url = "http://example.com/doc.html"
        key = "some_dedup_key"

        with CheckpointStore(db_path) as s:
            s.mark_url_processed(url)
            s.add_dedup_key(key)

        with CheckpointStore(db_path) as s:
            assert s.is_url_processed(url) is True
            assert s.has_dedup_key(key) is True

    def test_checkpoint_used_to_skip_on_resume(self, tmp_path):
        """
        Simulates an interrupted run: URL was processed, dedup key exists.
        On resume, the URL is skipped (is_url_processed returns True).
        """
        db_path = tmp_path / "checkpoints.db"
        url = "http://example.com/doc.html"
        key = "LS_2023_5_debate_test_1"

        # First run: process and checkpoint
        with CheckpointStore(db_path) as s:
            assert not s.is_url_processed(url)
            s.add_dedup_key(key)
            s.mark_url_processed(url)

        # Resumed run: URL should be skipped
        with CheckpointStore(db_path) as s:
            assert s.is_url_processed(url) is True
            assert s.has_dedup_key(key) is True


class TestContextManager:
    def test_context_manager_opens_and_closes(self, tmp_path):
        db_path = tmp_path / "checkpoints.db"
        with CheckpointStore(db_path) as s:
            s.add_dedup_key("test_key")
        assert s._conn is None  # closed after __exit__

    def test_error_without_open_raises(self, tmp_path):
        store = CheckpointStore(tmp_path / "checkpoints.db")
        with pytest.raises(RuntimeError, match="not open"):
            store.is_url_processed("http://example.com/doc.html")
