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

COI_DAY_URL = "https://www.constitutionofindia.net/debates/09-dec-1946/"
COI_DAY_HTML = (_FIXTURES / "coi_day.html").read_text()


# ── Test helpers ──────────────────────────────────────────────────────────────

class MockIndexer:
    """
    Records index_record() calls and simulates raw_documents in-memory store.
    Supports the Phase 12 two-stage pipeline (Stage 1 write + Stage 2 read).
    """

    def __init__(self):
        self.indexed_records: list[dict] = []
        self._raw_docs: dict[str, dict] = {}  # canonical_doc_id → row

    def index_record(self, record: dict, checkpoint: CheckpointStore) -> bool:
        self.indexed_records.append(record)
        return True

    def check_raw_document_exists(self, canonical_doc_id: str) -> bool:
        return canonical_doc_id in self._raw_docs

    def write_raw_document(
        self,
        canonical_doc_id: str,
        corpus: str,
        date,
        provider: str,
        format: str,
        extracted_text,
        metadata_json: dict,
        fetch_url,
        citation_url,
    ) -> None:
        if canonical_doc_id in self._raw_docs:
            return  # no-op on PK conflict
        import json
        # Simulate JSON roundtrip (tuples → lists in metadata)
        meta_serialized = json.loads(json.dumps(metadata_json, default=str))
        self._raw_docs[canonical_doc_id] = {
            "canonical_doc_id": canonical_doc_id,
            "corpus": corpus,
            "date": date,
            "provider": provider,
            "format": format,
            "extracted_text": extracted_text,
            "metadata_json": meta_serialized,
            "fetch_url": fetch_url,
            "citation_url": citation_url,
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

    async def test_sequence_assigned_at_orchestrator_level(self):
        """Records from fixture page get 1-based sequence_within_sitting assigned."""
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
            assert len(indexer.indexed_records) == 3  # fixture has 3 speeches
            sequences = [r.get("sequence_within_sitting") for r in indexer.indexed_records]
            assert sequences == [1, 2, 3], f"Expected [1,2,3], got {sequences}"
        finally:
            checkpoint.close()

    async def test_sequence_unique_within_sitting(self):
        """No two records from the same sitting share a sequence number."""
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
            sequences = [r.get("sequence_within_sitting") for r in indexer.indexed_records]
            assert len(set(sequences)) == len(sequences), "Duplicate sequence numbers found"
        finally:
            checkpoint.close()

    async def test_ca_date_always_derived_from_url_slug(self):
        """CA date must be derived from URL slug regardless of HTML body date."""
        url = "https://www.constitutionofindia.net/debates/volume-1/09-dec-1946/"
        doc_ref = _make_doc_ref(url=url)
        provider = StubProvider([doc_ref], {url: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                assert record.get("date") == "1946-12-09", (
                    f"CA date must be from URL slug '09-dec-1946' → '1946-12-09', "
                    f"got {record.get('date')!r}"
                )
        finally:
            checkpoint.close()

    async def test_ca_date_url_slug_overrides_html_body_date(self):
        """Even when HTML contains a different date, URL slug date is used."""
        # The coi_day.html fixture title says '9 December 1946' → same date,
        # but the slug check ensures the slug is ALWAYS the authoritative source.
        url = "https://www.constitutionofindia.net/debates/volume-1/27-aug-1947/"
        doc_ref = _make_doc_ref(url=url)
        # The fixture HTML has no parseable date in its body; the URL slug date
        # must still be used and must not be contaminated by any body content.
        provider = StubProvider([doc_ref], {url: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            for record in indexer.indexed_records:
                # Must be '1947-08-27' (from URL), not '1946-12-09' (from HTML title)
                assert record.get("date") == "1947-08-27", (
                    f"CA date must use URL slug '27-aug-1947' even when HTML says otherwise. "
                    f"Got: {record.get('date')!r}"
                )
        finally:
            checkpoint.close()

    async def test_ca_speeches_have_lang_original(self):
        """All CA speech records must have a lang_original field."""
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
                assert "lang_original" in record
                assert record["lang_original"] in ("en", "hi", "mixed")
        finally:
            checkpoint.close()

    async def test_ca_speeches_have_word_count_or_none(self):
        """word_count is an int when full_text_en is non-null; None otherwise."""
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
                if record.get("full_text_en") is not None:
                    assert isinstance(record.get("word_count"), int)
                    assert record["word_count"] > 0
                else:
                    assert record.get("word_count") is None
        finally:
            checkpoint.close()

    async def test_ca_per_speech_subjects_from_section_headers(self):
        """CA speeches carry subjects from section-header DOM walk."""
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
            assert len(indexer.indexed_records) == 3
            # Fixture: speeches 1+2 under "Objectives Resolution", speech 3 under "The Question of Procedure"
            subjects = [r.get("subject") for r in indexer.indexed_records]
            assert subjects[0] == "Objectives Resolution"
            assert subjects[1] == "Objectives Resolution"
            assert subjects[2] == "The Question of Procedure"
        finally:
            checkpoint.close()

    async def test_full_month_name_url_slug_parsed_correctly(self):
        """URLs with full month names (e.g. 29-july-1947) must be parsed to a valid date."""
        url = "https://www.constitutionofindia.net/debates/29-july-1947/"
        doc_ref = _make_doc_ref(url=url)
        provider = StubProvider([doc_ref], {url: COI_DAY_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()

        client = AsyncMock(spec=httpx.AsyncClient)
        orchestrator = CAOrchestrator(
            client=client, checkpoint=checkpoint, indexer=indexer, provider=provider
        )
        await orchestrator.run()

        try:
            # Document must not be skipped due to date-parse failure
            assert len(indexer.indexed_records) >= 1, (
                "Expected speeches indexed for full-month-name URL; got 0. "
                "Check _extract_ca_date_from_url month mapping."
            )
            for record in indexer.indexed_records:
                assert record.get("date") == "1947-07-29"
        finally:
            checkpoint.close()


# ── Unit tests for _extract_ca_date_from_url ─────────────────────────────────

class TestExtractCADateFromUrl:
    """Unit tests for _extract_ca_date_from_url covering all slug formats."""

    def _call(self, url: str) -> str | None:
        from ingest.sources.ca import _extract_ca_date_from_url
        return _extract_ca_date_from_url(url)

    def test_three_letter_month_abbr(self):
        assert self._call("https://www.constitutionofindia.net/debates/09-dec-1946/") == "1946-12-09"

    def test_full_month_name_july(self):
        assert self._call("https://www.constitutionofindia.net/debates/29-july-1947/") == "1947-07-29"

    def test_full_month_name_august(self):
        assert self._call("https://www.constitutionofindia.net/debates/08-august-1947/") == "1947-08-08"

    def test_full_month_name_september(self):
        assert self._call("https://www.constitutionofindia.net/debates/17-september-1949/") == "1949-09-17"

    def test_full_month_name_october(self):
        assert self._call("https://www.constitutionofindia.net/debates/01-october-1949/") == "1949-10-01"

    def test_full_month_name_november(self):
        assert self._call("https://www.constitutionofindia.net/debates/14-november-1949/") == "1949-11-14"

    def test_full_month_name_december(self):
        assert self._call("https://www.constitutionofindia.net/debates/15-december-1946/") == "1946-12-15"

    def test_iso_format_slug(self):
        assert self._call("https://www.constitutionofindia.net/debates/volume-1/1946-12-09/") == "1946-12-09"

    def test_case_insensitive_month(self):
        assert self._call("https://www.constitutionofindia.net/debates/09-DEC-1946/") == "1946-12-09"

    def test_unrecognised_slug_returns_none(self):
        assert self._call("https://www.constitutionofindia.net/debates/volume-1/") is None

    def test_no_trailing_slash_handled(self):
        assert self._call("https://www.constitutionofindia.net/debates/09-dec-1946") == "1946-12-09"
