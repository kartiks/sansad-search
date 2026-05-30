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


class TestDocumentTracking:
    def test_document_not_processed_initially(self, store):
        assert store.is_document_processed("12345") is False

    def test_document_processed_after_mark(self, store):
        store.mark_document_processed("12345", corpus="LS", provider="internet_archive")
        assert store.is_document_processed("12345") is True

    def test_other_document_not_affected(self, store):
        store.mark_document_processed("12345", corpus="LS")
        assert store.is_document_processed("99999") is False

    def test_processed_document_count(self, store):
        store.mark_document_processed("11111", corpus="LS")
        store.mark_document_processed("22222", corpus="RS")
        assert store.processed_document_count() == 2

    def test_mark_document_idempotent(self, store):
        store.mark_document_processed("12345", corpus="LS")
        store.mark_document_processed("12345", corpus="LS")  # second call should not raise
        assert store.processed_document_count() == 1

    def test_mark_stores_corpus_provider_fetch_url(self, tmp_path):
        db_path = tmp_path / "checkpoints.db"
        with CheckpointStore(db_path) as s:
            s.mark_document_processed(
                "12345",
                corpus="LS",
                provider="internet_archive",
                fetch_url="https://archive.org/download/eparlib.nic.in.12345/eparlib.nic.in.12345_djvu.txt",
            )
            conn = s._conn
            row = conn.execute(
                "SELECT corpus, provider, fetch_url FROM processed_documents "
                "WHERE canonical_doc_id = ?",
                ("12345",),
            ).fetchone()
        assert row[0] == "LS"
        assert row[1] == "internet_archive"
        assert "eparlib.nic.in.12345" in row[2]

    def test_ca_day_url_as_canonical_doc_id(self, store):
        """CA uses the day-URL as canonical_doc_id (single provider, no handle number)."""
        doc_id = "https://www.constitutionofindia.net/debates/volume1/1946-12-09"
        store.mark_document_processed(doc_id, corpus="CA", provider="coi_html")
        assert store.is_document_processed(doc_id) is True

    def test_ls_rs_handle_number_as_canonical_doc_id(self, store):
        """LS/RS use the DSpace handle number N as canonical_doc_id."""
        store.mark_document_processed("67890", corpus="LS", provider="eparlib_dspace",
                                       fetch_url="https://eparlib.sansad.in/handle/123456789/67890")
        assert store.is_document_processed("67890") is True
        # A different handle is not affected
        assert store.is_document_processed("11111") is False


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
        doc_id = "12345"
        key = "some_dedup_key"

        with CheckpointStore(db_path) as s:
            s.mark_document_processed(doc_id, corpus="LS")
            s.add_dedup_key(key)

        with CheckpointStore(db_path) as s:
            assert s.is_document_processed(doc_id) is True
            assert s.has_dedup_key(key) is True

    def test_checkpoint_used_to_skip_on_resume(self, tmp_path):
        """
        Simulates an interrupted run: document was processed, dedup key exists.
        On resume, the document is skipped (is_document_processed returns True).
        """
        db_path = tmp_path / "checkpoints.db"
        doc_id = "67890"
        key = "LS_2023_5_debate_test_1"

        with CheckpointStore(db_path) as s:
            assert not s.is_document_processed(doc_id)
            s.add_dedup_key(key)
            s.mark_document_processed(doc_id, corpus="LS", provider="internet_archive")

        with CheckpointStore(db_path) as s:
            assert s.is_document_processed(doc_id) is True
            assert s.has_dedup_key(key) is True

    def test_cross_provider_dedup_via_canonical_doc_id(self, tmp_path):
        """
        IA eparlib.nic.in.N and DSpace 123456789/N share the same handle N.
        Checkpointing with canonical_doc_id=N prevents double-fetch regardless
        of which provider originally satisfied the document.
        """
        db_path = tmp_path / "checkpoints.db"
        handle_n = "54321"

        with CheckpointStore(db_path) as s:
            # Satisfied by IA
            s.mark_document_processed(
                handle_n, corpus="LS", provider="internet_archive",
                fetch_url="https://archive.org/download/eparlib.nic.in.54321/..._djvu.txt",
            )

        with CheckpointStore(db_path) as s:
            # DSpace fallback would use the same canonical_doc_id
            assert s.is_document_processed(handle_n) is True


class TestContextManager:
    def test_context_manager_opens_and_closes(self, tmp_path):
        db_path = tmp_path / "checkpoints.db"
        with CheckpointStore(db_path) as s:
            s.add_dedup_key("test_key")
        assert s._conn is None  # closed after __exit__

    def test_error_without_open_raises(self, tmp_path):
        store = CheckpointStore(tmp_path / "checkpoints.db")
        with pytest.raises(RuntimeError, match="not open"):
            store.is_document_processed("any_id")
