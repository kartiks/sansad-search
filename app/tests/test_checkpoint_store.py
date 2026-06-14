"""Tests for ingest.checkpoints.store — PostgreSQL-backed checkpoint store.

The store now lives in PostgreSQL (psycopg2 + DATABASE_URL), so these tests run
against a live database and are skipped when TEST_DATABASE_URL is not set — the
same pattern as test_schema.py. Unit tests that only need a checkpoint interface
(orchestrator/indexer tests) use tests.fakes.FakeCheckpointStore instead.

Covered:
  - processed_documents tracking (existence, idempotent insert, cross-corpus
    isolation, provider/fetch_url, count, corpus clear)
  - ingestion_dedup_keys tracking (pre-filter; explicit + derived corpus)
  - persistence + resumability across a reconnect (close → reopen)
  - context-manager + use-before-open guard
  - INF-R1: interrupt → resume → identical record count, no duplicates
  - ARCHITECTURE §8 item 7: the dedup mirror must NOT suppress a legitimate insert
    after a selective clear (speeches + processed_documents cleared,
    ingestion_dedup_keys left intact) — re-run Stage 2 re-creates the rows
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import psycopg2
import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

_CHECKPOINT_TABLES = ("processed_documents", "ingestion_dedup_keys")
_ALL_TABLES = (
    "speeches",
    "qa_exchanges",
    "raw_documents",
    "processed_documents",
    "ingestion_dedup_keys",
)


@pytest.fixture(scope="session")
def pg_dsn():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set — skipping PostgreSQL checkpoint tests")
    # Ensure the schema exists (idempotent — CREATE … IF NOT EXISTS throughout).
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()
    return dsn


@pytest.fixture(autouse=True)
def clean_tables(pg_dsn):
    """Truncate all ingestion tables before each test for isolation."""
    conn = psycopg2.connect(pg_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"TRUNCATE {', '.join(_ALL_TABLES)} RESTART IDENTITY CASCADE"
            )
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture()
def store(pg_dsn):
    with CheckpointStore(pg_dsn) as s:
        yield s


# ── Helpers ─────────────────────────────────────────────────────────────────


def _speech_record(sequence: int = 1, source: str = "LS", canonical_doc_id="doc-1"):
    return {
        "record_type": "speech",
        "source": source,
        "proceeding_type": "debate",
        "date": "2023-03-15",
        "sitting_number": 5,
        "speaker_name": "Test Member",
        "sequence_within_sitting": sequence,
        "full_text_en": "Some text.",
        "lang_original": "en",
        "is_translated": False,
        "has_untranslated_content": False,
        "speaker_name_unresolved": False,
        "canonical_doc_id": canonical_doc_id,
    }


def _count(dsn: str, table: str) -> int:
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
    finally:
        conn.close()


# ── processed_documents ───────────────────────────────────────────────────────


class TestDocumentTracking:
    def test_document_not_processed_initially(self, store):
        assert store.is_document_processed("12345", "LS") is False

    def test_document_processed_after_mark(self, store):
        store.mark_document_processed("12345", corpus="LS", provider="internet_archive")
        assert store.is_document_processed("12345", "LS") is True

    def test_other_document_not_affected(self, store):
        store.mark_document_processed("12345", corpus="LS")
        assert store.is_document_processed("99999", "LS") is False

    def test_cross_corpus_isolation(self, store):
        """LS processing of handle N must not suppress RS processing of the same N."""
        store.mark_document_processed("12345", corpus="LS")
        assert store.is_document_processed("12345", "LS") is True
        assert store.is_document_processed("12345", "RS") is False

    def test_processed_document_count(self, store):
        store.mark_document_processed("11111", corpus="LS")
        store.mark_document_processed("22222", corpus="RS")
        assert store.processed_document_count() == 2

    def test_mark_document_idempotent(self, store):
        store.mark_document_processed("12345", corpus="LS")
        store.mark_document_processed("12345", corpus="LS")  # ON CONFLICT no-op
        assert store.processed_document_count() == 1

    def test_mark_stores_corpus_provider_fetch_url(self, store, pg_dsn):
        store.mark_document_processed(
            "12345",
            corpus="LS",
            provider="internet_archive",
            fetch_url="https://archive.org/download/eparlib.nic.in.12345/..._djvu.txt",
        )
        conn = psycopg2.connect(pg_dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT corpus, provider, fetch_url FROM processed_documents "
                    "WHERE canonical_doc_id = %s",
                    ("12345",),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        assert row[0] == "LS"
        assert row[1] == "internet_archive"
        assert "eparlib.nic.in.12345" in row[2]

    def test_ca_day_url_as_canonical_doc_id(self, store):
        doc_id = "https://www.constitutionofindia.net/debates/volume1/1946-12-09"
        store.mark_document_processed(doc_id, corpus="CA", provider="coi_html")
        assert store.is_document_processed(doc_id, "CA") is True

    def test_clear_corpus_deletes_only_that_corpus(self, store):
        store.mark_document_processed("a", corpus="LS")
        store.mark_document_processed("b", corpus="LS")
        store.mark_document_processed("c", corpus="RS")
        deleted = store.clear_corpus("LS")
        assert deleted == 2
        assert store.is_document_processed("a", "LS") is False
        assert store.is_document_processed("c", "RS") is True


# ── ingestion_dedup_keys ──────────────────────────────────────────────────────


class TestDedupKeyTracking:
    def test_key_absent_initially(self, store):
        assert store.has_dedup_key("LS_2023-03-15_5_debate_narendra_modi_3") is False

    def test_key_present_after_add(self, store):
        key = "LS_2023-03-15_5_debate_narendra_modi_3"
        store.add_dedup_key(key, "LS")
        assert store.has_dedup_key(key) is True

    def test_corpus_derived_from_key_prefix_when_omitted(self, store):
        """add_dedup_key derives corpus from the source prefix when not passed."""
        store.add_dedup_key("RS_2021-01-01_2_debate_speaker_1")  # no corpus arg
        assert store.has_dedup_key("RS_2021-01-01_2_debate_speaker_1") is True

    def test_other_key_not_affected(self, store):
        store.add_dedup_key("LS_a", "LS")
        assert store.has_dedup_key("LS_b") is False

    def test_add_key_idempotent(self, store):
        key = "CA_1946-12-09_1_debate_x_1"
        store.add_dedup_key(key, "CA")
        store.add_dedup_key(key, "CA")  # ON CONFLICT no-op
        assert store.dedup_key_count() == 1

    def test_dedup_key_count(self, store):
        store.add_dedup_key("LS_key_a", "LS")
        store.add_dedup_key("RS_key_b", "RS")
        assert store.dedup_key_count() == 2


# ── Resumability / persistence ────────────────────────────────────────────────


class TestResumability:
    def test_store_persists_across_open_close(self, pg_dsn):
        """Data written in one session is visible after close/reopen (reconnect)."""
        doc_id = "12345"
        key = "LS_persist_key"
        with CheckpointStore(pg_dsn) as s:
            s.mark_document_processed(doc_id, corpus="LS")
            s.add_dedup_key(key, "LS")
        with CheckpointStore(pg_dsn) as s:
            assert s.is_document_processed(doc_id, "LS") is True
            assert s.has_dedup_key(key) is True

    def test_checkpoint_used_to_skip_on_resume(self, pg_dsn):
        doc_id = "67890"
        with CheckpointStore(pg_dsn) as s:
            assert not s.is_document_processed(doc_id, "LS")
            s.mark_document_processed(doc_id, corpus="LS", provider="internet_archive")
        with CheckpointStore(pg_dsn) as s:
            assert s.is_document_processed(doc_id, "LS") is True

    def test_cross_provider_dedup_via_canonical_doc_id(self, pg_dsn):
        """IA eparlib.nic.in.N and DSpace 123456789/N share handle N → one checkpoint."""
        handle_n = "54321"
        with CheckpointStore(pg_dsn) as s:
            s.mark_document_processed(
                handle_n, corpus="LS", provider="internet_archive",
                fetch_url="https://archive.org/download/eparlib.nic.in.54321/..._djvu.txt",
            )
        with CheckpointStore(pg_dsn) as s:
            assert s.is_document_processed(handle_n, "LS") is True

    def test_interrupt_resume_identical_count_no_duplicates(self, pg_dsn):
        """INF-R1: interrupted run + resumed run == clean run, with no duplicate rows."""
        records = [_speech_record(sequence=i + 1) for i in range(3)]
        meili = MagicMock()
        pg = psycopg2.connect(pg_dsn)
        indexer = Indexer(pg, meili, pg_dsn=pg_dsn)
        try:
            # Interrupted run: index records 0-1, then "crash" (no doc checkpoint).
            with CheckpointStore(pg_dsn) as cp:
                for r in records[:2]:
                    indexer.index_record(r, cp)
            assert _count(pg_dsn, "speeches") == 2

            # Resumed run: re-process the full corpus. ON CONFLICT skips 0-1.
            with CheckpointStore(pg_dsn) as cp:
                for r in records:
                    indexer.index_record(r, cp)
        finally:
            pg.close()

        # Identical to a clean run (3 distinct records), no duplicates.
        assert _count(pg_dsn, "speeches") == 3


# ── ARCHITECTURE §8 item 7 — dedup mirror must not suppress legitimate inserts ──


class TestDedupMirrorInvariant:
    def test_reinsert_after_selective_clear_recreates_rows(self, pg_dsn):
        """
        Selective re-processing (DEPLOYMENT §6.4): clear speeches + processed_documents
        for a scope but leave ingestion_dedup_keys intact, then re-run Stage 2. The
        rows MUST be re-created — the dedup mirror is a pre-filter only and the
        authoritative guard is the speeches UNIQUE(dedup_key) ON CONFLICT.
        """
        record = _speech_record()
        meili = MagicMock()
        pg = psycopg2.connect(pg_dsn)
        indexer = Indexer(pg, meili, pg_dsn=pg_dsn)
        try:
            # ── Initial Stage 2: index + checkpoint the document ──────────────
            with CheckpointStore(pg_dsn) as cp:
                assert indexer.index_record(record, cp) is True
                cp.mark_document_processed("doc-1", corpus="LS")
            assert _count(pg_dsn, "speeches") == 1
            assert _count(pg_dsn, "ingestion_dedup_keys") == 1
            assert _count(pg_dsn, "processed_documents") == 1

            # ── Selective clear: speeches + processed_documents ONLY ──────────
            with pg.cursor() as cur:
                cur.execute("DELETE FROM speeches WHERE source = 'LS'")
                cur.execute("DELETE FROM processed_documents WHERE corpus = 'LS'")
            pg.commit()
            assert _count(pg_dsn, "speeches") == 0
            # The dedup mirror is deliberately left intact.
            assert _count(pg_dsn, "ingestion_dedup_keys") == 1

            # ── Re-run Stage 2: the row MUST be re-created despite the mirror ──
            with CheckpointStore(pg_dsn) as cp:
                assert cp.has_dedup_key(_expected_key()) is True  # mirror intact
                reinserted = indexer.index_record(record, cp)
            assert reinserted is True
        finally:
            pg.close()

        assert _count(pg_dsn, "speeches") == 1


def _expected_key() -> str:
    """The dedup key the indexer builds for _speech_record() (DATA-MODELS §1.5)."""
    from ingest.indexer import build_dedup_key

    return build_dedup_key(_speech_record())


# ── Context manager / guards ──────────────────────────────────────────────────


class TestContextManager:
    def test_context_manager_opens_and_closes(self, pg_dsn):
        with CheckpointStore(pg_dsn) as s:
            s.add_dedup_key("LS_ctx_key", "LS")
        assert s._conn is None  # closed after __exit__

    def test_error_without_open_raises(self, pg_dsn):
        s = CheckpointStore(pg_dsn)
        with pytest.raises(RuntimeError, match="not open"):
            s.is_document_processed("any_id", "LS")
