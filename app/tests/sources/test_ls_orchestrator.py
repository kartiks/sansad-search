"""
Integration tests for the updated ingest.sources.ls.LSOrchestrator.

Verifies:
  - IA provider path produces ia_text records (correct provider and format).
  - DSpace fallback invoked only for items absent from IA (document-level dedup).
  - Re-run against a fully-processed fixture corpus produces zero new records.
  - Provider chain ordering: IA first, DSpace second.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.sources._provider import DocumentRef, Provider
from ingest.sources.ls import LSOrchestrator

# ── Helpers ───────────────────────────────────────────────────────────────────

IA_DJVU_TEXT = (
    "SHRI NARENDRA MODI:\n"
    "Mr. Speaker, I rise to speak on this important matter.\n"
    "The government is committed to economic development.\n"
    "\n"
    "SHRI RAHUL GANDHI:\n"
    "Mr. Speaker, I wish to respond to the Prime Minister.\n"
    "The government must be held accountable.\n"
)


class MockIndexer:
    """Records index_record() calls; always returns True."""

    def __init__(self):
        self.indexed_records: list[dict] = []

    def index_record(self, record: dict, checkpoint: CheckpointStore) -> bool:
        self.indexed_records.append(record)
        return True


class StubProvider(Provider):
    """Stub provider returning fixed DocumentRefs and canned content."""

    def __init__(
        self,
        doc_refs: list[DocumentRef],
        contents: dict[str, str | bytes | None],
        name: str = "stub",
    ) -> None:
        self._doc_refs = doc_refs
        self._contents = contents
        self.name = name
        self.fetch_calls: list[str] = []

    async def discover(self) -> list[DocumentRef]:
        return list(self._doc_refs)

    async def fetch(self, doc_ref: DocumentRef) -> str | bytes | None:
        self.fetch_calls.append(doc_ref.canonical_doc_id)
        return self._contents.get(doc_ref.canonical_doc_id)


def _make_ia_doc_ref(handle_n: str, date: str = "2023-03-15") -> DocumentRef:
    identifier = f"eparlib.nic.in.{handle_n}"
    return DocumentRef(
        corpus="LS",
        provider="internet_archive",
        format="ia_text",
        fetch_url=f"https://archive.org/download/{identifier}/{identifier}_djvu.txt",
        canonical_doc_id=handle_n,
        citation_url=f"https://eparlib.sansad.in/handle/123456789/{handle_n}",
        metadata={
            "identifier": identifier,
            "eparlib_document_url": f"https://eparlib.sansad.in/handle/123456789/{handle_n}",
            "eparlib_date": date,
            "eparlib_lok_sabha_number": "17",
            "eparlib_session_number": "8",
            "eparlib_title": "Lok Sabha Debates",
        },
    )


def _make_dspace_doc_ref(handle_n: str) -> DocumentRef:
    item_url = f"https://eparlib.sansad.in/handle/123456789/{handle_n}"
    return DocumentRef(
        corpus="LS",
        provider="eparlib_dspace",
        format="pdf",
        fetch_url=item_url,
        canonical_doc_id=handle_n,
        citation_url=item_url,
        metadata={"item_url": item_url},
    )


def _make_checkpoint() -> CheckpointStore:
    store = CheckpointStore(Path(":memory:"))
    store.open()
    return store


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLSOrchestratorProviderChain:
    async def test_ia_path_produces_records_with_ia_text_format(self):
        """IA provider path (format=ia_text) is parsed and records are indexed."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider(
            [ia_ref], {"12345": IA_DJVU_TEXT}, name="ia"
        )
        dspace_provider = StubProvider([], {}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider, dspace_provider],
        )
        stats = await orchestrator.run()

        try:
            assert stats["indexed"] >= 1
            assert len(indexer.indexed_records) >= 1
        finally:
            checkpoint.close()

    async def test_dspace_fallback_not_invoked_for_ia_documents(self):
        """
        When IA processes document N, DSpace must not fetch N again.
        The checkpoint from the IA run causes the DSpace DocumentRef for the
        same handle_n to be skipped.
        """
        handle_n = "12345"
        ia_ref = _make_ia_doc_ref(handle_n)
        dspace_ref = _make_dspace_doc_ref(handle_n)  # same handle → same canonical_doc_id

        ia_provider = StubProvider([ia_ref], {handle_n: IA_DJVU_TEXT}, name="ia")
        dspace_provider = StubProvider([dspace_ref], {handle_n: b"%PDF"}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider, dspace_provider],
        )
        await orchestrator.run()

        try:
            # DSpace must not have been asked to fetch the document that IA already processed
            assert handle_n not in dspace_provider.fetch_calls
        finally:
            checkpoint.close()

    async def test_dspace_fallback_invoked_for_ia_missing_items(self):
        """DSpace fetch IS invoked for documents that IA did not discover."""
        ia_handle = "11111"
        dspace_only_handle = "99999"

        ia_ref = _make_ia_doc_ref(ia_handle)
        dspace_ref = _make_dspace_doc_ref(dspace_only_handle)

        ia_provider = StubProvider(
            [ia_ref], {ia_handle: IA_DJVU_TEXT}, name="ia"
        )
        dspace_provider = StubProvider(
            [dspace_ref], {dspace_only_handle: None}, name="dspace"
        )

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider, dspace_provider],
        )
        await orchestrator.run()

        try:
            # DSpace IS asked to fetch the document IA didn't have
            assert dspace_only_handle in dspace_provider.fetch_calls
        finally:
            checkpoint.close()

    async def test_rerun_produces_zero_new_records(self):
        """Re-running against a fully-processed corpus produces zero new records."""
        ia_ref = _make_ia_doc_ref("12345")
        dspace_ref = _make_dspace_doc_ref("12345")  # same doc as IA

        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")
        dspace_provider = StubProvider([dspace_ref], {"12345": b"%PDF"}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider, dspace_provider],
        )

        # First run
        await orchestrator.run()
        first_count = len(indexer.indexed_records)
        assert first_count >= 1

        # Second run — checkpoint is still populated
        indexer.indexed_records.clear()
        ia_provider2 = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia2")
        dspace_provider2 = StubProvider([dspace_ref], {"12345": b"%PDF"}, name="dspace2")
        orchestrator2 = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider2, dspace_provider2],
        )
        stats2 = await orchestrator2.run()

        try:
            assert stats2["indexed"] == 0
            assert len(indexer.indexed_records) == 0
        finally:
            checkpoint.close()

    async def test_document_checkpointed_after_ia_processing(self):
        """After IA processes a document, it appears in the checkpoint store."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            assert checkpoint.is_document_processed("12345")
        finally:
            checkpoint.close()

    async def test_ia_fetch_failure_counted_as_error(self):
        """When IA fetch() returns None, the document is counted as an error."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": None}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        stats = await orchestrator.run()

        try:
            assert stats["errors"] == 1
            assert stats["indexed"] == 0
        finally:
            checkpoint.close()

    async def test_no_archive_org_url_in_citation_url(self):
        """citation_url in all records must never be an archive.org URL (Non-Neg #9)."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                url = record.get("source_url")
                if url is not None:
                    assert "archive.org" not in url
        finally:
            checkpoint.close()

    async def test_records_have_source_ls(self):
        """All indexed records from LS orchestrator must have source='LS'."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source") == "LS"
        finally:
            checkpoint.close()

    async def test_unrecognised_format_logs_warning_and_skips(self):
        """_parse must log a warning and return None for an unrecognised doc_ref.format."""
        import logging

        unknown_ref = DocumentRef(
            corpus="LS",
            provider="stub",
            format="xml",  # not ia_text or pdf
            fetch_url="https://example.com/doc.xml",
            canonical_doc_id="99999",
            citation_url="https://example.com/doc.xml",
            metadata={},
        )
        unknown_provider = StubProvider([unknown_ref], {"99999": b"<xml/>"}, name="stub")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[unknown_provider],
        )

        class _WarnCapture(logging.Handler):
            def __init__(self):
                super().__init__(logging.WARNING)
                self.messages: list[str] = []

            def emit(self, record):
                self.messages.append(record.getMessage())

        handler = _WarnCapture()
        ls_logger = logging.getLogger("ingest.sources.ls")
        ls_logger.addHandler(handler)
        try:
            await orchestrator.run()
        finally:
            ls_logger.removeHandler(handler)

        assert any("unrecognised format" in m for m in handler.messages), (
            "expected warning about unrecognised format, got: " + str(handler.messages)
        )
        assert len(indexer.indexed_records) == 0

    async def test_records_have_no_ocr_low_confidence_field(self):
        """ocr_low_confidence must not appear in any LS record (dropped in Phase 7)."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert "ocr_low_confidence" not in record
        finally:
            checkpoint.close()

    async def test_source_url_equals_eparlib_document_url_for_ia_records(self):
        """LS-via-IA records must have source_url == eparlib_document_url (Non-Neg #9 positive)."""
        ia_ref = _make_ia_doc_ref("12345")
        ia_provider = StubProvider([ia_ref], {"12345": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            expected_url = "https://eparlib.sansad.in/handle/123456789/12345"
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source_url") == expected_url, (
                    f"expected source_url={expected_url!r}, got {record.get('source_url')!r}"
                )
        finally:
            checkpoint.close()

    async def test_qa_branch_produces_qa_records_for_starred_question(self):
        """Orchestrator routes starred_question title to segment_qa, producing record_type='qa'."""
        handle_n = "55555"
        identifier = f"eparlib.nic.in.{handle_n}"

        IA_QA_TEXT = (
            "STARRED QUESTION NO. 1\n\n"
            "SHRI TEST QUESTIONER:\n"
            "Will the Minister of Finance please state the government's fiscal policy "
            "for the current financial year?\n\n"
            "THE MINISTER OF FINANCE:\n"
            "The government is fully committed to fiscal consolidation and economic growth.\n"
        )

        qa_ref = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url=f"https://archive.org/download/{identifier}/{identifier}_djvu.txt",
            canonical_doc_id=handle_n,
            citation_url=f"https://eparlib.sansad.in/handle/123456789/{handle_n}",
            metadata={
                "identifier": identifier,
                "eparlib_document_url": f"https://eparlib.sansad.in/handle/123456789/{handle_n}",
                "eparlib_date": "2023-03-15",
                "eparlib_lok_sabha_number": "17",
                "eparlib_session_number": "8",
                "eparlib_title": "Lok Sabha Starred Questions",
            },
        )

        ia_provider = StubProvider([qa_ref], {handle_n: IA_QA_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider],
        )
        await orchestrator.run()

        try:
            assert len(indexer.indexed_records) >= 1, (
                "expected at least one Q+A record; got none"
            )
            for record in indexer.indexed_records:
                assert record.get("record_type") == "qa", (
                    f"expected record_type='qa', got {record.get('record_type')!r}"
                )
        finally:
            checkpoint.close()

    async def test_dspace_fallback_when_ia_fetch_fails(self):
        """IA discovers N but fetch→None (error, not checkpointed); DSpace must still process N."""
        handle_n = "77777"
        ia_ref = _make_ia_doc_ref(handle_n)
        dspace_ref = _make_dspace_doc_ref(handle_n)

        # IA discovers N but fetch fails
        ia_provider = StubProvider([ia_ref], {handle_n: None}, name="ia")
        # DSpace also discovers N; content is irrelevant — key assertion is the fetch call
        dspace_provider = StubProvider([dspace_ref], {handle_n: None}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = LSOrchestrator(
            client=client,
            checkpoint=checkpoint,
            indexer=indexer,
            providers=[ia_provider, dspace_provider],
        )
        stats = await orchestrator.run()

        try:
            # IA reported the fetch as an error, not a skip
            assert stats["errors"] >= 1
            # Document was NOT checkpointed by IA (fetch failed), so DSpace must attempt it
            assert handle_n in dspace_provider.fetch_calls, (
                "DSpace should have fetched N after IA fetch failed; "
                f"fetch_calls={dspace_provider.fetch_calls!r}"
            )
        finally:
            checkpoint.close()
