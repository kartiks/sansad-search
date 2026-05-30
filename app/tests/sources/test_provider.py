"""Tests for ingest.sources._provider — DocumentRef dataclass and Provider contract."""
from __future__ import annotations

import pytest

from ingest.sources._provider import DocumentRef, Provider


class TestDocumentRef:
    def test_required_fields(self):
        doc_ref = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/download/eparlib.nic.in.12345/eparlib.nic.in.12345_djvu.txt",
            canonical_doc_id="12345",
            citation_url="https://eparlib.sansad.in/handle/123456789/12345",
        )
        assert doc_ref.corpus == "LS"
        assert doc_ref.provider == "internet_archive"
        assert doc_ref.format == "ia_text"
        assert doc_ref.canonical_doc_id == "12345"
        assert "archive.org" not in doc_ref.citation_url

    def test_citation_url_can_be_none(self):
        """RS-via-IA with no derivable DSpace handle: citation_url=None (PRD v1.3 edge case)."""
        doc_ref = DocumentRef(
            corpus="RS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/download/eparlib.nic.in.99999/..._djvu.txt",
            canonical_doc_id="99999",
            citation_url=None,
        )
        assert doc_ref.citation_url is None

    def test_metadata_defaults_to_empty_dict(self):
        doc_ref = DocumentRef(
            corpus="CA",
            provider="coi_html",
            format="html",
            fetch_url="https://www.constitutionofindia.net/debates/volume1/1946-12-09",
            canonical_doc_id="https://www.constitutionofindia.net/debates/volume1/1946-12-09",
            citation_url="https://www.constitutionofindia.net/debates/volume1/1946-12-09",
        )
        assert doc_ref.metadata == {}

    def test_metadata_stored(self):
        meta = {"eparlib_date": "2023-03-15", "eparlib_session_number": "261"}
        doc_ref = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/...",
            canonical_doc_id="12345",
            citation_url="https://eparlib.sansad.in/handle/123456789/12345",
            metadata=meta,
        )
        assert doc_ref.metadata["eparlib_date"] == "2023-03-15"

    def test_format_values(self):
        """format must be one of html, pdf, or ia_text."""
        for fmt in ("html", "pdf", "ia_text"):
            doc_ref = DocumentRef(
                corpus="LS",
                provider="test",
                format=fmt,
                fetch_url="https://example.com/doc",
                canonical_doc_id="1",
                citation_url=None,
            )
            assert doc_ref.format == fmt

    def test_ca_day_url_as_canonical_doc_id(self):
        """CA uses the per-day page URL as canonical_doc_id (single provider)."""
        url = "https://www.constitutionofindia.net/debates/volume1/1946-12-09"
        doc_ref = DocumentRef(
            corpus="CA",
            provider="coi_html",
            format="html",
            fetch_url=url,
            canonical_doc_id=url,
            citation_url=url,
        )
        assert doc_ref.canonical_doc_id == url

    def test_ls_rs_handle_number_as_canonical_doc_id(self):
        """LS/RS use DSpace handle number N as canonical_doc_id."""
        doc_ref = DocumentRef(
            corpus="LS",
            provider="internet_archive",
            format="ia_text",
            fetch_url="https://archive.org/download/eparlib.nic.in.54321/..._djvu.txt",
            canonical_doc_id="54321",
            citation_url="https://eparlib.sansad.in/handle/123456789/54321",
        )
        assert doc_ref.canonical_doc_id == "54321"


class TestProviderContract:
    def test_provider_is_abstract(self):
        """Provider cannot be instantiated directly — must subclass and implement abstract methods."""
        with pytest.raises(TypeError):
            Provider()

    def test_concrete_provider_must_implement_discover_and_fetch(self):
        """A concrete Provider that implements both methods can be instantiated."""

        class ConcreteProvider(Provider):
            async def discover(self):
                return []

            async def fetch(self, doc_ref):
                return None

        provider = ConcreteProvider()
        assert hasattr(provider, "discover")
        assert hasattr(provider, "fetch")

    def test_partial_implementation_raises(self):
        """A provider implementing only discover (not fetch) raises TypeError."""
        class PartialProvider(Provider):
            async def discover(self):
                return []

        with pytest.raises(TypeError):
            PartialProvider()

    @pytest.mark.asyncio
    async def test_discover_returns_list(self):
        class TestProvider(Provider):
            async def discover(self):
                return [
                    DocumentRef(
                        corpus="LS",
                        provider="test",
                        format="ia_text",
                        fetch_url="https://example.com/doc",
                        canonical_doc_id="1",
                        citation_url=None,
                    )
                ]

            async def fetch(self, doc_ref):
                return "some content"

        provider = TestProvider()
        refs = await provider.discover()
        assert isinstance(refs, list)
        assert len(refs) == 1
        assert isinstance(refs[0], DocumentRef)

    @pytest.mark.asyncio
    async def test_fetch_returns_content_or_none(self):
        class TestProvider(Provider):
            async def discover(self):
                return []

            async def fetch(self, doc_ref):
                if doc_ref.canonical_doc_id == "valid":
                    return b"PDF content"
                return None

        provider = TestProvider()
        doc_ref_valid = DocumentRef(
            corpus="LS", provider="test", format="pdf",
            fetch_url="https://example.com/doc.pdf",
            canonical_doc_id="valid", citation_url=None,
        )
        doc_ref_invalid = DocumentRef(
            corpus="LS", provider="test", format="pdf",
            fetch_url="https://example.com/missing.pdf",
            canonical_doc_id="missing", citation_url=None,
        )
        assert await provider.fetch(doc_ref_valid) == b"PDF content"
        assert await provider.fetch(doc_ref_invalid) is None
