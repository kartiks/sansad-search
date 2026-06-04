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
from unittest.mock import AsyncMock, MagicMock, patch

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
    """
    Records index_record() calls and simulates raw_documents in-memory store.
    Supports the Phase 12 two-stage pipeline.
    """

    def __init__(self):
        self.indexed_records: list[dict] = []
        self._raw_docs: dict[str, dict] = {}

    def index_record(self, record: dict, checkpoint: CheckpointStore) -> bool:
        self.indexed_records.append(record)
        return True

    def check_raw_document_exists(self, canonical_doc_id: str) -> bool:
        return canonical_doc_id in self._raw_docs

    def write_raw_document(
        self, canonical_doc_id, corpus, date, provider, format,
        extracted_text, metadata_json, fetch_url, citation_url,
    ) -> None:
        if canonical_doc_id in self._raw_docs:
            return
        import json
        meta = json.loads(json.dumps(metadata_json, default=str))
        self._raw_docs[canonical_doc_id] = {
            "canonical_doc_id": canonical_doc_id, "corpus": corpus, "date": date,
            "provider": provider, "format": format, "extracted_text": extracted_text,
            "metadata_json": meta, "fetch_url": fetch_url, "citation_url": citation_url,
        }

    def read_raw_documents_for_scope(self, corpus, date_from=None, date_to=None):
        for row in self._raw_docs.values():
            if row["corpus"] != corpus:
                continue
            if date_from and row["date"] and str(row["date"]) < date_from:
                continue
            if date_to and row["date"] and str(row["date"]) > date_to:
                continue
            yield dict(row)


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


# ── Phase 10: Shared sequence assignment ──────────────────────────────────────

class TestLSSharedSequence:
    """sequence_within_sitting is assigned at orchestrator level (not segmenter)."""

    def _make_ia_content_for_qa(self, handle_n: str) -> str:
        """IA text content for a starred_question document."""
        return (
            "STARRED QUESTION NO. 42\n\n"
            "SHRI QUESTIONER:\nWhat is the policy on infrastructure?\n\n"
            "SHRI MINISTER OF FINANCE:\nThe government has invested significantly.\n"
        )

    async def test_speech_records_get_sequence_from_orchestrator(self):
        """Speech records produced by LS orchestrator have sequence_within_sitting set."""
        handle = "99001"
        metadata = {
            "identifier": f"eparlib.nic.in.{handle}",
            "eparlib_document_url": f"https://eparlib.sansad.in/handle/123456789/{handle}",
            "eparlib_date": "2023-03-15",
            "title": "Lok Sabha Debates",
        }
        doc_ref = _make_ia_doc_ref(handle, date="2023-03-15")
        ia_content = IA_DJVU_TEXT

        ia_provider = StubProvider([doc_ref], {handle: ia_content}, name="ia")
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
                assert "sequence_within_sitting" in record
                assert isinstance(record["sequence_within_sitting"], int)
                assert record["sequence_within_sitting"] >= 1
        finally:
            checkpoint.close()

    async def test_sequences_unique_within_same_sitting(self):
        """No two records from the same sitting share a sequence number."""
        handle1 = "99002"
        handle2 = "99003"
        # Both documents for the same sitting date
        doc_ref1 = _make_ia_doc_ref(handle1, date="2023-03-15")
        doc_ref2 = _make_ia_doc_ref(handle2, date="2023-03-15")
        doc_ref2 = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url=f"https://archive.org/download/eparlib.nic.in.{handle2}/eparlib.nic.in.{handle2}_djvu.txt",
            canonical_doc_id=handle2,
            citation_url=f"https://eparlib.sansad.in/handle/123456789/{handle2}",
            metadata={
                "identifier": f"eparlib.nic.in.{handle2}",
                "eparlib_document_url": f"https://eparlib.sansad.in/handle/123456789/{handle2}",
                "eparlib_date": "2023-03-15",
                "title": "Lok Sabha Debates",
            },
        )

        ia_provider = StubProvider(
            [doc_ref1, doc_ref2],
            {handle1: IA_DJVU_TEXT, handle2: IA_DJVU_TEXT},
            name="ia",
        )
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
            sitting_records = [
                r for r in indexer.indexed_records
                if r.get("date") == "2023-03-15"
            ]
            sequences = [r.get("sequence_within_sitting") for r in sitting_records]
            assert len(set(sequences)) == len(sequences), (
                f"Duplicate sequence numbers in same sitting: {sequences}"
            )
        finally:
            checkpoint.close()

    async def test_sequence_shared_across_speech_and_qa_types_in_same_sitting(self):
        """sequence_within_sitting is a shared counter: no number appears in both speech
        and Q+A records from the same sitting."""
        debate_handle = "99010"
        qa_handle = "99011"
        date = "2023-04-01"

        debate_ref = _make_ia_doc_ref(debate_handle, date=date)
        # Override title so the QA doc is detected as starred_question proceeding type
        qa_ref = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url=f"https://archive.org/download/eparlib.nic.in.{qa_handle}/eparlib.nic.in.{qa_handle}_djvu.txt",
            canonical_doc_id=qa_handle,
            citation_url=f"https://eparlib.sansad.in/handle/123456789/{qa_handle}",
            metadata={
                "identifier": f"eparlib.nic.in.{qa_handle}",
                "eparlib_document_url": f"https://eparlib.sansad.in/handle/123456789/{qa_handle}",
                "eparlib_date": date,
                "eparlib_lok_sabha_number": "17",
                "eparlib_session_number": "8",
                "eparlib_title": "Starred Questions — 1 April 2023",
            },
        )
        qa_content = self._make_ia_content_for_qa(qa_handle)

        provider = StubProvider(
            [debate_ref, qa_ref],
            {debate_handle: IA_DJVU_TEXT, qa_handle: qa_content},
            name="ia",
        )
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        orchestrator = LSOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
        )
        await orchestrator.run()

        try:
            sitting_records = [r for r in indexer.indexed_records if r.get("date") == date]
            speech_records = [r for r in sitting_records if r.get("record_type") == "speech"]
            qa_records = [r for r in sitting_records if r.get("record_type") == "qa"]

            assert len(speech_records) >= 1, "Expected at least one speech record from debate doc"
            assert len(qa_records) >= 1, "Expected at least one Q+A record from starred_question doc"

            all_seqs = [r["sequence_within_sitting"] for r in sitting_records]
            assert len(set(all_seqs)) == len(all_seqs), (
                f"sequence_within_sitting collision across speech+Q+A types: {all_seqs}"
            )
        finally:
            checkpoint.close()

    async def test_records_have_lang_original(self):
        """All LS records must have lang_original set."""
        handle = "99004"
        doc_ref = _make_ia_doc_ref(handle)
        ia_provider = StubProvider([doc_ref], {handle: IA_DJVU_TEXT}, name="ia")
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        orchestrator = LSOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, providers=[ia_provider]
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert "lang_original" in record
                assert record["lang_original"] in ("en", "hi", "mixed")
        finally:
            checkpoint.close()


# ── Stage 1 date filtering ────────────────────────────────────────────────────

class TestLSStage1DateFilter:
    """run_stage1(date_from, date_to) post-parse gate skips out-of-window docs."""

    async def test_run_stage1_skips_document_before_date_from(self):
        """Document whose parsed date < date_from is counted as skipped, not written."""
        early_ref = _make_ia_doc_ref("11111", date="2023-06-01")
        provider = StubProvider([early_ref], {"11111": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(LSOrchestrator, "_parse", return_value={"date": "2023-06-01", "source": "LS", "proceeding_type": "debate"}):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1(date_from="2024-01-01")

        try:
            assert "11111" not in indexer._raw_docs, "pre-date_from doc must not be written"
            assert stats["fetched"] == 0
            assert stats["skipped"] == 1
        finally:
            checkpoint.close()

    async def test_run_stage1_skips_document_after_date_to(self):
        """Document whose parsed date > date_to is counted as skipped, not written."""
        late_ref = _make_ia_doc_ref("22222", date="2024-05-01")
        provider = StubProvider([late_ref], {"22222": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(LSOrchestrator, "_parse", return_value={"date": "2024-05-01", "source": "LS", "proceeding_type": "debate"}):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1(date_to="2024-03-31")

        try:
            assert "22222" not in indexer._raw_docs, "post-date_to doc must not be written"
            assert stats["fetched"] == 0
            assert stats["skipped"] == 1
        finally:
            checkpoint.close()

    async def test_run_stage1_writes_in_window_and_skips_out_of_window(self):
        """With a date window, only in-window docs are written; out-of-window are skipped."""
        in_ref = _make_ia_doc_ref("33333", date="2024-02-15")
        out_ref = _make_ia_doc_ref("44444", date="2024-07-01")
        provider = StubProvider(
            [in_ref, out_ref],
            {"33333": IA_DJVU_TEXT, "44444": IA_DJVU_TEXT},
            name="ia",
        )

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        def _parse_side(content, doc_ref):
            date_map = {"33333": "2024-02-15", "44444": "2024-07-01"}
            return {"date": date_map[doc_ref.canonical_doc_id], "source": "LS", "proceeding_type": "debate"}

        with patch.object(LSOrchestrator, "_parse", side_effect=_parse_side):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1(date_from="2024-01-01", date_to="2024-03-31")

        try:
            assert "33333" in indexer._raw_docs, "in-window doc must be written"
            assert "44444" not in indexer._raw_docs, "out-of-window doc must be skipped"
            assert stats["fetched"] == 1
            assert stats["skipped"] == 1
        finally:
            checkpoint.close()

    async def test_run_stage1_writes_document_on_exact_date_from(self):
        """Doc whose parsed date == date_from (inclusive lower bound) must be written."""
        ref = _make_ia_doc_ref("66666", date="2024-01-01")
        provider = StubProvider([ref], {"66666": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(LSOrchestrator, "_parse", return_value={"date": "2024-01-01", "source": "LS", "proceeding_type": "debate"}):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1(date_from="2024-01-01")

        try:
            assert "66666" in indexer._raw_docs, "doc on exact date_from must be written (>= not >)"
            assert stats["fetched"] == 1
            assert stats["skipped"] == 0
        finally:
            checkpoint.close()

    async def test_run_stage1_writes_document_on_exact_date_to(self):
        """Doc whose parsed date == date_to (inclusive upper bound) must be written."""
        ref = _make_ia_doc_ref("77777", date="2024-03-31")
        provider = StubProvider([ref], {"77777": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(LSOrchestrator, "_parse", return_value={"date": "2024-03-31", "source": "LS", "proceeding_type": "debate"}):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1(date_to="2024-03-31")

        try:
            assert "77777" in indexer._raw_docs, "doc on exact date_to must be written (<= not <)"
            assert stats["fetched"] == 1
            assert stats["skipped"] == 0
        finally:
            checkpoint.close()

    async def test_run_stage1_no_filter_writes_all(self):
        """Without date_from/date_to, all documents are written regardless of date."""
        ref = _make_ia_doc_ref("55555", date="2024-01-15")
        provider = StubProvider([ref], {"55555": IA_DJVU_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(LSOrchestrator, "_parse", return_value={"date": "2024-01-15", "source": "LS", "proceeding_type": "debate"}):
            orchestrator = LSOrchestrator(
                client=client, checkpoint=checkpoint, indexer=indexer, providers=[provider]
            )
            stats = await orchestrator.run_stage1()

        try:
            assert "55555" in indexer._raw_docs, "doc must be written when no date filter"
            assert stats["fetched"] == 1
        finally:
            checkpoint.close()
