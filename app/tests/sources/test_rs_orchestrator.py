"""
Integration tests for ingest.sources.rs.RSOrchestrator (Phase 9).

Verifies the RS provider chain [sansad_rs_html, internet_archive, rsdebate_dspace]
and the PRD v1.3 canonical-citation rule:

  - sansad.in/rs HTML records are produced for recent sittings (format=html).
  - IA fallback processes documents the HTML front-end did not cover.
  - DSpace fallback processes documents IA did not cover (document-level dedup).
  - No record's source_url is ever an archive.org URL (Non-Negotiable #9).
  - source_url on every indexed record == doc_ref.citation_url, for ALL formats
    (html / ia_text / pdf) — the RS canonical-citation rule.
  - The RS-via-IA no-handle edge case: citation_url=None → source_url=None.
  - Re-run against a fully-processed corpus produces zero new records.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.sources._provider import DocumentRef, Provider
from ingest.sources.providers.internet_archive import InternetArchiveProvider
from ingest.sources.providers.rsdebate_dspace import RsdebateDspaceProvider
from ingest.sources.providers.sansad_rs_html import SansadRsHtmlProvider
from ingest.sources.rs import RSOrchestrator

# ── Helpers ───────────────────────────────────────────────────────────────────

_SPEECH_TEXT = (
    "SHRI TEST MEMBER:\n"
    "Mr. Chairman, I rise to speak on this important matter before the House.\n"
    "The government must address the concerns of the people.\n"
    "\n"
    "SHRI SECOND MEMBER:\n"
    "Mr. Chairman, I wish to respond to the honourable member.\n"
    "These concerns have already been addressed by the ministry.\n"
)

_SANSAD_HTML = (
    "<html><head><title>Rajya Sabha Debate - 15 March 2023</title></head>"
    "<body><div class='content'>"
    "<h1>Rajya Sabha Debate - 15 March 2023</h1>"
    f"<pre>{_SPEECH_TEXT}</pre>"
    "</div></body></html>"
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


def _make_sansad_doc_ref(date_iso: str = "2023-03-15") -> DocumentRef:
    url = f"https://sansad.in/rs/debates/officials/{date_iso.replace('-', '/')}"
    return DocumentRef(
        corpus="RS",
        provider="sansad_rs_html",
        format="html",
        fetch_url=url,
        canonical_doc_id=url,
        citation_url=url,
        metadata={"sitting_date": date_iso},
    )


def _make_ia_doc_ref(handle_n: str) -> DocumentRef:
    identifier = f"eparlib.nic.in.{handle_n}"
    citation = f"https://rsdebate.nic.in/handle/123456789/{handle_n}"
    return DocumentRef(
        corpus="RS",
        provider="internet_archive",
        format="ia_text",
        fetch_url=f"https://archive.org/download/{identifier}/{identifier}_djvu.txt",
        canonical_doc_id=handle_n,
        citation_url=citation,
        metadata={"identifier": identifier, "eparlib_date": "2018-02-12"},
    )


def _make_dspace_doc_ref(handle_n: str) -> DocumentRef:
    item_url = f"https://rsdebate.nic.in/handle/123456789/{handle_n}"
    return DocumentRef(
        corpus="RS",
        provider="rsdebate_dspace",
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


def _orchestrator(providers, checkpoint, indexer):
    return RSOrchestrator(
        client=AsyncMock(spec=httpx.AsyncClient),
        checkpoint=checkpoint,
        indexer=indexer,
        providers=providers,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRSOrchestratorDefaultProviderChain:
    """Gap 1: production default chain membership and order are exercised."""

    def test_default_provider_chain_order_and_membership(self):
        """RSOrchestrator() with no providers arg uses the correct production chain in order."""
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            orc = RSOrchestrator(
                client=AsyncMock(spec=httpx.AsyncClient),
                checkpoint=checkpoint,
                indexer=indexer,
            )
            assert len(orc._providers) == 3
            assert isinstance(orc._providers[0], SansadRsHtmlProvider)
            assert isinstance(orc._providers[1], InternetArchiveProvider)
            assert orc._providers[1]._corpus == "RS"
            assert isinstance(orc._providers[2], RsdebateDspaceProvider)
        finally:
            checkpoint.close()


class TestRSOrchestratorProviderChain:
    async def test_sansad_html_records_produced_for_recent_sitting(self):
        """sansad.in/rs HTML (format=html) is parsed and indexed for a recent sitting."""
        ref = _make_sansad_doc_ref()
        html_provider = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            stats = await _orchestrator([html_provider], checkpoint, indexer).run()
            assert stats["indexed"] >= 1
            assert len(indexer.indexed_records) >= 1
        finally:
            checkpoint.close()

    async def test_records_have_source_rs(self):
        ref = _make_sansad_doc_ref()
        html_provider = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([html_provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source") == "RS"
        finally:
            checkpoint.close()

    async def test_source_url_equals_citation_url_for_html_records(self):
        """RS canonical-citation rule: source_url == doc_ref.citation_url (html format)."""
        ref = _make_sansad_doc_ref()
        html_provider = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([html_provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source_url") == ref.citation_url
        finally:
            checkpoint.close()

    async def test_source_url_equals_rsdebate_url_for_ia_records(self):
        """RS-via-IA records cite rsdebate.nic.in (derived from handle), never archive.org."""
        ref = _make_ia_doc_ref("55501")
        ia_provider = StubProvider([ref], {"55501": _SPEECH_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([ia_provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source_url") == "https://rsdebate.nic.in/handle/123456789/55501"
                assert "archive.org" not in (record.get("source_url") or "")
        finally:
            checkpoint.close()

    async def test_no_handle_edge_case_yields_null_source_url(self):
        """PRD v1.3 edge case: IA RS item with citation_url=None → source_url=None (never archive.org)."""
        identifier = "rs_untagged_item"
        ref = DocumentRef(
            corpus="RS",
            provider="internet_archive",
            format="ia_text",
            fetch_url=f"https://archive.org/download/{identifier}/{identifier}_djvu.txt",
            canonical_doc_id=identifier,
            citation_url=None,  # no derivable DSpace handle
            metadata={"identifier": identifier},
        )
        ia_provider = StubProvider([ref], {identifier: _SPEECH_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([ia_provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("source_url") is None
        finally:
            checkpoint.close()

    async def test_ia_fallback_for_items_html_did_not_cover(self):
        """IA processes a document the sansad HTML front-end did not discover."""
        html_ref = _make_sansad_doc_ref("2023-03-15")
        ia_ref = _make_ia_doc_ref("55501")

        html_provider = StubProvider(
            [html_ref], {html_ref.canonical_doc_id: _SANSAD_HTML}, name="html"
        )
        ia_provider = StubProvider([ia_ref], {"55501": _SPEECH_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([html_provider, ia_provider], checkpoint, indexer).run()
            assert "55501" in ia_provider.fetch_calls
        finally:
            checkpoint.close()

    async def test_dspace_fallback_not_invoked_for_ia_documents(self):
        """When IA processes handle N, DSpace must not fetch N again (document-level dedup)."""
        handle_n = "55501"
        ia_ref = _make_ia_doc_ref(handle_n)
        dspace_ref = _make_dspace_doc_ref(handle_n)  # same handle → same canonical_doc_id

        ia_provider = StubProvider([ia_ref], {handle_n: _SPEECH_TEXT}, name="ia")
        dspace_provider = StubProvider([dspace_ref], {handle_n: b"%PDF"}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([ia_provider, dspace_provider], checkpoint, indexer).run()
            assert handle_n not in dspace_provider.fetch_calls
        finally:
            checkpoint.close()

    async def test_dspace_fallback_invoked_for_ia_missing_items(self):
        """DSpace fetch IS invoked for documents IA did not discover."""
        ia_ref = _make_ia_doc_ref("11111")
        dspace_ref = _make_dspace_doc_ref("99999")

        ia_provider = StubProvider([ia_ref], {"11111": _SPEECH_TEXT}, name="ia")
        dspace_provider = StubProvider([dspace_ref], {"99999": None}, name="dspace")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([ia_provider, dspace_provider], checkpoint, indexer).run()
            assert "99999" in dspace_provider.fetch_calls
        finally:
            checkpoint.close()

    async def test_no_archive_org_url_in_any_source_url(self):
        """No indexed record's source_url is ever an archive.org URL (Non-Neg #9)."""
        html_ref = _make_sansad_doc_ref()
        ia_ref = _make_ia_doc_ref("55501")

        html_provider = StubProvider(
            [html_ref], {html_ref.canonical_doc_id: _SANSAD_HTML}, name="html"
        )
        ia_provider = StubProvider([ia_ref], {"55501": _SPEECH_TEXT}, name="ia")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([html_provider, ia_provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                url = record.get("source_url")
                if url is not None:
                    assert "archive.org" not in url
        finally:
            checkpoint.close()

    async def test_rerun_produces_zero_new_records(self):
        """Re-running against a fully-processed corpus produces zero new records (checkpoint skip)."""
        ref = _make_sansad_doc_ref()
        provider1 = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider1], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1

            indexer.indexed_records.clear()
            provider2 = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html2")
            stats2 = await _orchestrator([provider2], checkpoint, indexer).run()

            assert stats2["indexed"] == 0
            assert len(indexer.indexed_records) == 0
            assert stats2["skipped"] >= 1
        finally:
            checkpoint.close()

    async def test_document_checkpointed_after_processing(self):
        ref = _make_sansad_doc_ref()
        provider = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider], checkpoint, indexer).run()
            assert checkpoint.is_document_processed(ref.canonical_doc_id)
        finally:
            checkpoint.close()

    async def test_fetch_failure_counted_as_error(self):
        ref = _make_sansad_doc_ref()
        provider = StubProvider([ref], {ref.canonical_doc_id: None}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            stats = await _orchestrator([provider], checkpoint, indexer).run()
            assert stats["errors"] == 1
            assert stats["indexed"] == 0
            # Resumability: a failed fetch must NOT checkpoint the document so it
            # is retried on resume (mirrors test_ls_orchestrator.py:489).
            assert not checkpoint.is_document_processed(ref.canonical_doc_id)
        finally:
            checkpoint.close()

    async def test_parse_exception_counted_as_error_not_checkpointed(self):
        """Gap 3a: parse_html raising an exception → errors+=1, indexed==0, not checkpointed."""
        ref = _make_sansad_doc_ref()
        provider = StubProvider([ref], {ref.canonical_doc_id: _SANSAD_HTML}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            with patch("ingest.sources.rs.parse_html", side_effect=RuntimeError("parse boom")):
                stats = await _orchestrator([provider], checkpoint, indexer).run()
            assert stats["errors"] == 1
            assert stats["indexed"] == 0
            assert not checkpoint.is_document_processed(ref.canonical_doc_id)
        finally:
            checkpoint.close()

    async def test_unrecognised_format_counted_as_error_not_checkpointed(self):
        """Gap 3b: DocumentRef with unknown format → errors+=1, indexed==0, not checkpointed."""
        url = "https://sansad.in/rs/debates/officials/2023/03/15"
        ref = DocumentRef(
            corpus="RS",
            provider="sansad_rs_html",
            format="unknown_format",
            fetch_url=url,
            canonical_doc_id=url,
            citation_url=url,
            metadata={},
        )
        provider = StubProvider([ref], {url: b"some content"}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            stats = await _orchestrator([provider], checkpoint, indexer).run()
            assert stats["errors"] == 1
            assert stats["indexed"] == 0
            assert not checkpoint.is_document_processed(url)
        finally:
            checkpoint.close()

    async def test_qa_branch_produces_qa_records_for_starred_question(self):
        """A starred-question HTML title routes to segment_qa, producing record_type='qa'."""
        url = "https://sansad.in/rs/debates/officials/2023/03/15"
        qa_html = (
            "<html><head><title>Rajya Sabha Starred Questions - 15 March 2023</title></head>"
            "<body><div class='content'>"
            "<h1>Rajya Sabha Starred Questions - 15 March 2023</h1>"
            "<pre>STARRED QUESTION NO. 1\n\n"
            "SHRI TEST QUESTIONER:\n"
            "Will the Minister please state the government's policy on this matter?\n\n"
            "THE MINISTER:\n"
            "The government is fully committed to addressing this issue.\n</pre>"
            "</div></body></html>"
        )
        ref = DocumentRef(
            corpus="RS",
            provider="sansad_rs_html",
            format="html",
            fetch_url=url,
            canonical_doc_id=url,
            citation_url=url,
            metadata={"sitting_date": "2023-03-15"},
        )
        provider = StubProvider([ref], {url: qa_html}, name="html")

        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert record.get("record_type") == "qa"
        finally:
            checkpoint.close()


# ── Phase 10: Shared sequence assignment ──────────────────────────────────────

class TestRSSharedSequence:
    """sequence_within_sitting is assigned at orchestrator level for RS records."""

    async def test_rs_speech_records_get_sequence(self):
        """RS speech records produced by RSOrchestrator have sequence_within_sitting."""
        doc_id = "rs-sansad-2023-03-15"
        doc_ref = DocumentRef(
            corpus="RS",
            provider="sansad_rs_html",
            format="html",
            fetch_url="https://sansad.in/rs/debates/2023-03-15",
            canonical_doc_id=doc_id,
            citation_url="https://sansad.in/rs/debates/2023-03-15",
            metadata={},
        )
        provider = StubProvider(
            [doc_ref],
            {doc_id: _SANSAD_HTML},
        )
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider], checkpoint, indexer).run()
            assert len(indexer.indexed_records) >= 1
            for record in indexer.indexed_records:
                assert "sequence_within_sitting" in record
                assert isinstance(record["sequence_within_sitting"], int)
                assert record["sequence_within_sitting"] >= 1
        finally:
            checkpoint.close()

    async def test_sequences_unique_in_sitting(self):
        """No two RS records from the same sitting have the same sequence number."""
        doc_id1 = "rs-sansad-2023-03-16-a"
        doc_id2 = "rs-sansad-2023-03-16-b"
        def make_ref(doc_id):
            return DocumentRef(
                corpus="RS",
                provider="sansad_rs_html",
                format="html",
                fetch_url=f"https://sansad.in/rs/debates/2023-03-16/{doc_id}",
                canonical_doc_id=doc_id,
                citation_url=f"https://sansad.in/rs/debates/2023-03-16/{doc_id}",
                metadata={},
            )
        html_with_date = (
            "<html><head><title>Rajya Sabha Debate - 16 March 2023</title></head>"
            "<body><div class='content'>"
            "<h1>Rajya Sabha Debate - 16 March 2023</h1>"
            f"<pre>{_SPEECH_TEXT}</pre>"
            "</div></body></html>"
        )
        provider = StubProvider(
            [make_ref(doc_id1), make_ref(doc_id2)],
            {doc_id1: html_with_date, doc_id2: html_with_date},
        )
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider], checkpoint, indexer).run()
            sitting_records = [
                r for r in indexer.indexed_records
                if r.get("date") == "2023-03-16"
            ]
            sequences = [r.get("sequence_within_sitting") for r in sitting_records]
            if len(sequences) > 1:
                assert len(set(sequences)) == len(sequences), (
                    f"Duplicate sequence numbers: {sequences}"
                )
        finally:
            checkpoint.close()

    async def test_rs_records_have_lang_original(self):
        """All RS records must have lang_original set."""
        doc_id = "rs-lang-test"
        doc_ref = DocumentRef(
            corpus="RS",
            provider="sansad_rs_html",
            format="html",
            fetch_url="https://sansad.in/rs/debates/lang-test",
            canonical_doc_id=doc_id,
            citation_url="https://sansad.in/rs/debates/lang-test",
            metadata={},
        )
        provider = StubProvider([doc_ref], {doc_id: _SANSAD_HTML})
        checkpoint = _make_checkpoint()
        indexer = MockIndexer()
        try:
            await _orchestrator([provider], checkpoint, indexer).run()
            for record in indexer.indexed_records:
                assert "lang_original" in record
                assert record["lang_original"] in ("en", "hi", "mixed")
        finally:
            checkpoint.close()
