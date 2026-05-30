"""Tests for ingest.sources.providers.eparlib_dspace — EparlibDspaceProvider."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._provider import DocumentRef
from ingest.sources.providers.eparlib_dspace import (
    EPARLIB_BASE,
    EPARLIB_BROWSE_URL,
    EparlibDspaceProvider,
    _extract_handle_number,
    _resolve_bitstream_url,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _browse_html() -> str:
    return (_FIXTURES / "eparlib_browse.html").read_text()


def _item_html() -> str:
    return (_FIXTURES / "eparlib_item.html").read_text()


# ── EPARLIB_BROWSE_URL constant ──────────────────────────────────────────────

class TestEparlibBrowseUrl:
    def test_default_browse_url_uses_collection_handle_7(self):
        """Default browse URL must scope discovery to the LS collection (handle /7)."""
        assert "/handle/123456789/7/browse" in EPARLIB_BROWSE_URL

    def test_default_browse_url_excludes_global_browse(self):
        """Global /browse endpoint returns all collections including CA-Legislative."""
        # Must not point at the unrestricted site-wide browse endpoint.
        assert EPARLIB_BROWSE_URL != f"{EPARLIB_BASE}/browse"


# ── _extract_handle_number ────────────────────────────────────────────────────

class TestExtractHandleNumber:
    def test_extracts_handle_from_full_url(self):
        url = "https://eparlib.sansad.in/handle/123456789/12345"
        assert _extract_handle_number(url) == "12345"

    def test_extracts_handle_from_relative_path(self):
        assert _extract_handle_number("/handle/123456789/99") == "99"

    def test_returns_none_for_non_handle_url(self):
        assert _extract_handle_number("https://eparlib.sansad.in/browse?type=dateissued") is None

    def test_returns_none_for_empty_string(self):
        assert _extract_handle_number("") is None


# ── _resolve_bitstream_url ────────────────────────────────────────────────────

class TestResolveBitstreamUrl:
    def test_extracts_bitstream_url_from_item_html(self):
        """Bitstream URL must be resolved from the item page HTML, never constructed."""
        html = _item_html()
        result = _resolve_bitstream_url(html, "https://eparlib.sansad.in/handle/123456789/12345")
        assert result is not None
        assert "/bitstream/" in result
        assert result.endswith(".pdf")

    def test_bitstream_url_is_absolute(self):
        html = _item_html()
        result = _resolve_bitstream_url(html, "https://eparlib.sansad.in/handle/123456789/12345")
        assert result is not None
        assert result.startswith("https://")

    def test_bitstream_url_never_constructed_from_filename_pattern(self):
        """The URL must come from the link in the page, not be built from a filename pattern."""
        html = _item_html()
        base_url = "https://eparlib.sansad.in/handle/123456789/12345"
        result = _resolve_bitstream_url(html, base_url)
        # Verify the URL matches what's actually in the fixture HTML
        assert result == "https://eparlib.sansad.in/bitstream/123456789/12345/1/lsd_17_08_15-03-2023.pdf"

    def test_returns_none_when_no_pdf_link(self):
        html = "<html><body><p>No files here.</p></body></html>"
        result = _resolve_bitstream_url(html, "https://eparlib.sansad.in/handle/123456789/12345")
        assert result is None

    def test_ignores_non_pdf_bitstream_links(self):
        html = """
        <html><body>
          <a href="/bitstream/123456789/12345/1/readme.txt">readme.txt</a>
        </body></html>
        """
        result = _resolve_bitstream_url(html, "https://eparlib.sansad.in/handle/123456789/12345")
        assert result is None


# ── EparlibDspaceProvider.discover() ─────────────────────────────────────────

class TestEparlibDspaceProviderDiscover:
    async def test_discovers_item_pages_from_browse_fixture(self):
        """Fixture browse page has 2 item links; should produce 2 DocumentRefs."""
        browse_resp_1 = MagicMock(status_code=200, text=_browse_html())
        browse_resp_2 = MagicMock(
            status_code=200,
            text="<html><body></body></html>",  # empty second page = end of pagination
        )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [browse_resp_1, browse_resp_2]

        provider = EparlibDspaceProvider(
            client,
            browse_url=f"{EPARLIB_BASE}/browse",
            rate_delay=0.0,
        )
        doc_refs = await provider.discover()

        assert len(doc_refs) == 2

    async def test_doc_ref_corpus_and_format(self):
        browse_resp_1 = MagicMock(status_code=200, text=_browse_html())
        browse_resp_2 = MagicMock(status_code=200, text="<html><body></body></html>")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [browse_resp_1, browse_resp_2]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.corpus == "LS"
            assert ref.format == "pdf"
            assert ref.provider == "eparlib_dspace"

    async def test_canonical_doc_id_is_handle_number(self):
        """canonical_doc_id must be the handle number N (shared with IA provider)."""
        browse_resp_1 = MagicMock(status_code=200, text=_browse_html())
        browse_resp_2 = MagicMock(status_code=200, text="<html><body></body></html>")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [browse_resp_1, browse_resp_2]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        doc_refs = await provider.discover()

        # Fixture has items at /handle/123456789/12345 and /handle/123456789/67890
        handle_numbers = {ref.canonical_doc_id for ref in doc_refs}
        assert "12345" in handle_numbers
        assert "67890" in handle_numbers

    async def test_citation_url_is_item_page_url(self):
        """citation_url is the DSpace item page URL, not an archive.org URL."""
        browse_resp_1 = MagicMock(status_code=200, text=_browse_html())
        browse_resp_2 = MagicMock(status_code=200, text="<html><body></body></html>")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [browse_resp_1, browse_resp_2]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.citation_url is not None
            assert "archive.org" not in ref.citation_url
            assert EPARLIB_BASE in ref.citation_url

    async def test_url_without_handle_number_skipped(self):
        """Item URLs that don't contain /handle/N/M are skipped."""
        bad_browse_html = """
        <html><body>
          <a href="/browse?type=dateissued">Browse</a>
          <a href="/handle/123456789/12345">Valid item</a>
        </body></html>
        """
        browse_resp_1 = MagicMock(status_code=200, text=bad_browse_html)
        browse_resp_2 = MagicMock(status_code=200, text="<html><body></body></html>")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [browse_resp_1, browse_resp_2]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        doc_refs = await provider.discover()

        # Only the valid /handle/ link produces a DocumentRef
        assert len(doc_refs) == 1


# ── EparlibDspaceProvider.fetch() ────────────────────────────────────────────

class TestEparlibDspaceProviderFetch:
    def _make_doc_ref(self) -> DocumentRef:
        item_url = f"{EPARLIB_BASE}/handle/123456789/12345"
        return DocumentRef(
            corpus="LS",
            provider="eparlib_dspace",
            format="pdf",
            fetch_url=item_url,
            canonical_doc_id="12345",
            citation_url=item_url,
            metadata={"item_url": item_url},
        )

    async def test_fetch_resolves_bitstream_from_item_page_not_filename(self):
        """Bitstream URL must come from the item page — never from a constructed filename."""
        item_resp = MagicMock(status_code=200, text=_item_html())
        pdf_bytes = b"%PDF-1.4 fixture pdf content"
        pdf_resp = MagicMock(status_code=200, content=pdf_bytes)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [item_resp, pdf_resp]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        result = await provider.fetch(self._make_doc_ref())

        assert isinstance(result, bytes)
        assert result == pdf_bytes
        # Verify the second GET was for the bitstream URL (not a constructed name)
        second_call_url = client.get.call_args_list[1][0][0]
        assert "/bitstream/" in second_call_url
        assert second_call_url.endswith(".pdf")

    async def test_fetch_two_step_http_calls(self):
        """fetch() must make exactly 2 HTTP calls: item page + PDF bitstream."""
        item_resp = MagicMock(status_code=200, text=_item_html())
        pdf_resp = MagicMock(status_code=200, content=b"%PDF")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [item_resp, pdf_resp]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        await provider.fetch(self._make_doc_ref())

        assert client.get.call_count == 2

    async def test_fetch_returns_none_when_item_page_fails(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=404)

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        result = await provider.fetch(self._make_doc_ref())

        assert result is None

    async def test_fetch_returns_none_when_no_bitstream_link(self):
        item_html_no_pdf = "<html><body><p>No files listed.</p></body></html>"
        item_resp = MagicMock(status_code=200, text=item_html_no_pdf)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = item_resp

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        result = await provider.fetch(self._make_doc_ref())

        assert result is None
        # Only one HTTP call made (item page); PDF fetch not attempted
        assert client.get.call_count == 1

    async def test_fetch_returns_none_when_pdf_fetch_fails(self):
        item_resp = MagicMock(status_code=200, text=_item_html())
        pdf_fail = MagicMock(status_code=503)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [item_resp] + [pdf_fail] * 4  # 1 + 3 retries

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = EparlibDspaceProvider(client, rate_delay=0.0)
            result = await provider.fetch(self._make_doc_ref())

        assert result is None

    async def test_fetch_returns_bytes(self):
        pdf_bytes = b"%PDF-1.4 real content"
        item_resp = MagicMock(status_code=200, text=_item_html())
        pdf_resp = MagicMock(status_code=200, content=pdf_bytes)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [item_resp, pdf_resp]

        provider = EparlibDspaceProvider(client, rate_delay=0.0)
        result = await provider.fetch(self._make_doc_ref())

        assert isinstance(result, bytes)
