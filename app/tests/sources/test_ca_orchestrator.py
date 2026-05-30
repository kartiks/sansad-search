"""
Integration tests for the updated ingest.sources.ca.CAOrchestrator.

Tests the full provider chain → parse → segment → index flow using:
  - A mock/stub Provider that returns fixture DocumentRefs without real HTTP
  - A real CheckpointStore backed by an in-memory SQLite database
  - A MockIndexer that records index_record() calls
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.sources._provider import DocumentRef, Provider
from ingest.sources.ca import CAOrchestrator

_FIXTURES = Path(__file__).parent.parent / "fixtures"

COI_DAY_URL = "https://www.constitutionofindia.net/debates/volume-1/1946-12-09/"
COI_DAY_HTML = (_FIXTURES / "coi_day.html").read_text()


# ── Test helpers ──────────────────────────────────────────────────────────────

class MockIndexer:
    """Records index_record() calls; always returns True (insert succeeds)."""

    def __init__(self):
        self.indexed_records: list[dict] = []

    def index_record(self, record: dict, checkpoint: CheckpointStore) -> bool:
        self.indexed_records.append(record)
        return True


class StubProvider(Provider):
    """
    Stub provider that returns a fixed list of DocumentRefs and canned content.

    Lets integration tests control exactly which documents are discovered and
    what HTML is returned, without making any real HTTP calls.
    """

    def __init__(
        self,
        doc_refs: list[DocumentRef],
        contents: dict[str, str | None],
    ) -> None:
        self._doc_refs = doc_refs
        self._contents = contents

    async def discover(self) -> list[DocumentRef]:
        return list(self._doc_refs)

    async def fetch(self, doc_ref: DocumentRef) -> str | None:
        return self._contents.get(doc_ref.canonical_doc_id)


def _make_doc_ref(url: str = COI_DAY_URL, volume: int = 1) -> DocumentRef:
    return DocumentRef(
        corpus="CA",
        provider="coi_html",
        format="html",
        fetch_url=url,
        canonical_doc_id=url,
        citation_url=url,
        metadata={"volume": volume},
    )


def _make_checkpoint() -> CheckpointStore:
    """Return a real CheckpointStore backed by an in-memory SQLite database."""
    store = CheckpointStore(Path(":memory:"))
    store.open()
    return store


# ── Integration tests ─────────────────────────────────────────────────────────

class TestCAOrchestratorRun:
    async def test_produces_ca_speech_records_from_fixture_html(self):
        """
        Running provider chain against mocked HTTP produces correctly segmented
        CA speech records. The fixture HTML (coi_day.html) has 3 speakers.
        """
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            provider=provider,
        )
        stats = await orchestrator.run()

        try:
            assert stats["indexed"] >= 1
            assert len(indexer.indexed_records) >= 1
        finally:
            checkpoint.close()

    async def test_records_have_source_ca(self):
        """All indexed records must have source='CA'."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert record.get("source") == "CA"
        finally:
            checkpoint.close()

    async def test_records_have_no_ocr_low_confidence_field(self):
        """ocr_low_confidence must not appear in any CA record (dropped in Phase 7)."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert "ocr_low_confidence" not in record
        finally:
            checkpoint.close()

    async def test_session_name_is_none_for_all_ca_records(self):
        """CA records must always have session_name = None (PRD spec)."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert record.get("session_name") is None
        finally:
            checkpoint.close()

    async def test_volume_metadata_propagated_to_records(self):
        """Records must carry the volume number from the DocumentRef metadata."""
        doc_ref = _make_doc_ref(volume=3)
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("volume") == 3
        finally:
            checkpoint.close()

    async def test_document_marked_processed_after_indexing(self):
        """After a successful run, the document must be in the checkpoint store."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            assert checkpoint.is_document_processed(COI_DAY_URL)
        finally:
            checkpoint.close()

    async def test_rerun_produces_zero_new_records(self):
        """Re-running against a fully-processed corpus produces zero new indexed records."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )

        # First run
        await orchestrator.run()
        first_run_count = len(indexer.indexed_records)

        # Second run — same checkpoint, same provider
        indexer.indexed_records.clear()
        stats2 = await orchestrator.run()

        try:
            assert stats2["indexed"] == 0
            assert len(indexer.indexed_records) == 0
            assert stats2["skipped"] == 1
        finally:
            checkpoint.close()

    async def test_fetch_failure_counted_as_error_not_crash(self):
        """When fetch() returns None, the document is skipped with an error count."""
        doc_ref = _make_doc_ref()
        provider = StubProvider([doc_ref], {COI_DAY_URL: None})  # fetch returns None
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        stats = await orchestrator.run()

        try:
            assert stats["errors"] == 1
            assert stats["indexed"] == 0
            assert len(indexer.indexed_records) == 0
        finally:
            checkpoint.close()

    async def test_multiple_documents_all_indexed(self):
        """Multiple DocumentRefs from discover() are all processed."""
        url1 = "https://www.constitutionofindia.net/debates/volume-1/1946-12-09/"
        url2 = "https://www.constitutionofindia.net/debates/volume-1/1946-12-11/"
        ref1 = _make_doc_ref(url=url1)
        ref2 = _make_doc_ref(url=url2)
        provider = StubProvider(
            [ref1, ref2],
            {url1: COI_DAY_HTML, url2: COI_DAY_HTML},
        )
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        stats = await orchestrator.run()

        try:
            assert stats["indexed"] >= 2  # At least 1 record per document
            assert checkpoint.is_document_processed(url1)
            assert checkpoint.is_document_processed(url2)
        finally:
            checkpoint.close()
