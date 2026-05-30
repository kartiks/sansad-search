"""Tests for ingest.sources._discovery — HTML listing crawl, DSpace browse, IA search."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.sources._discovery import (
    crawl_html_listing,
    enumerate_ia_search,
    paginate_dspace_browse,
)


def _mock_response(text: str = "", status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


def _mock_json_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = json.dumps(data)
    resp.json.return_value = data
    return resp


# ── crawl_html_listing ────────────────────────────────────────────────────────

class TestCrawlHtmlListing:
    @pytest.mark.asyncio
    async def test_extracts_absolute_links(self):
        html = """
        <html><body>
          <a href="/vol1/1946-12-09">Day 1</a>
          <a href="/vol1/1946-12-11">Day 2</a>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _mock_response(html)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await crawl_html_listing(client, "https://example.com/listing")
        assert "https://example.com/vol1/1946-12-09" in urls
        assert "https://example.com/vol1/1946-12-11" in urls

    @pytest.mark.asyncio
    async def test_link_filter_applied(self):
        html = """
        <html><body>
          <a href="/debates/day1">Day 1</a>
          <a href="/other/page">Other</a>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await crawl_html_listing(
                client,
                "https://example.com/listing",
                link_filter=lambda u: "/debates/" in u,
            )
        assert all("/debates/" in u for u in urls)
        assert not any("/other/" in u for u in urls)

    @pytest.mark.asyncio
    async def test_failed_fetch_returns_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=None))
            urls = await crawl_html_listing(client, "https://example.com/listing")
        assert urls == []

    @pytest.mark.asyncio
    async def test_fragment_links_excluded(self):
        html = '<html><body><a href="#section">Skip to section</a><a href="/page">Page</a></body></html>'
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await crawl_html_listing(client, "https://example.com/")
        assert all(not u.startswith("#") for u in urls)
        assert "https://example.com/page" in urls


# ── paginate_dspace_browse ────────────────────────────────────────────────────

class TestPaginateDspaceBrowse:
    @pytest.mark.asyncio
    async def test_collects_handle_links(self):
        html = """
        <html><body>
          <a href="/handle/123456789/1001">Item 1</a>
          <a href="/handle/123456789/1002">Item 2</a>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            # Returns same page twice; second call returns < rpp items (stopping)
            fetch_mock = AsyncMock(return_value=_mock_response(html))
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                rpp=20,
            )
        # Should include the handle URLs
        assert any("/handle/123456789/1001" in u for u in urls)
        assert any("/handle/123456789/1002" in u for u in urls)

    @pytest.mark.asyncio
    async def test_stops_pagination_when_fewer_than_rpp(self):
        """Pagination stops when a page returns fewer items than rpp."""
        html_with_1_item = """
        <html><body>
          <a href="/handle/123456789/1001">Only item</a>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_response(html_with_1_item)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            await paginate_dspace_browse(client, "https://example.com/browse", rpp=20)

        assert call_count == 1  # stopped after first page (1 < 20)

    @pytest.mark.asyncio
    async def test_failed_page_fetch_stops_pagination(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=None))
            urls = await paginate_dspace_browse(client, "https://example.com/browse")
        assert urls == []

    @pytest.mark.asyncio
    async def test_no_duplicate_urls(self):
        """Items appearing on multiple pages must appear only once in results."""
        html = """
        <html><body>
          <a href="/handle/123456789/1001">Item 1</a>
          <a href="/handle/123456789/1002">Item 2</a>
        </body></html>
        """
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First page: return 2 items (but rpp=2 so may paginate)
                return _mock_response(html)
            return _mock_response("")  # second page empty

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            urls = await paginate_dspace_browse(
                client, "https://example.com/browse", rpp=2
            )

        assert len(urls) == len(set(urls))  # no duplicates


# ── enumerate_ia_search ───────────────────────────────────────────────────────

class TestEnumerateIaSearch:
    @pytest.mark.asyncio
    async def test_collects_all_docs(self):
        data = {
            "response": {
                "docs": [
                    {"identifier": "eparlib.nic.in.1", "eparlib_document_url": "https://eparlib.sansad.in/handle/1"},
                    {"identifier": "eparlib.nic.in.2", "eparlib_document_url": "https://eparlib.sansad.in/handle/2"},
                ]
            }
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_json_response(data)))
            results = await enumerate_ia_search(client, "identifier:(eparlib.nic.in*)")
        assert len(results) == 2
        assert results[0]["identifier"] == "eparlib.nic.in.1"

    @pytest.mark.asyncio
    async def test_stops_when_docs_empty(self):
        data = {"response": {"docs": []}}
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_json_response(data)))
            results = await enumerate_ia_search(client, "identifier:(eparlib.nic.in*)")
        assert results == []

    @pytest.mark.asyncio
    async def test_paginates_multiple_pages(self):
        page1 = {"response": {"docs": [{"identifier": f"eparlib.nic.in.{i}"} for i in range(2)]}}
        page2 = {"response": {"docs": [{"identifier": "eparlib.nic.in.2"}]}}  # last page

        responses = [_mock_json_response(page1), _mock_json_response(page2)]
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            results = await enumerate_ia_search(
                client, "identifier:(eparlib.nic.in*)", rows=2
            )
        assert call_count == 2  # fetched two pages

    @pytest.mark.asyncio
    async def test_failed_fetch_returns_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=None))
            results = await enumerate_ia_search(client, "identifier:(eparlib.nic.in*)")
        assert results == []

    @pytest.mark.asyncio
    async def test_citation_url_never_archive_org(self):
        """Verify that IA enumeration returns eparlib URLs, not archive.org ones."""
        data = {
            "response": {
                "docs": [
                    {
                        "identifier": "eparlib.nic.in.12345",
                        "eparlib_document_url": "https://eparlib.sansad.in/handle/123456789/12345",
                    }
                ]
            }
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_json_response(data)))
            results = await enumerate_ia_search(
                client,
                "identifier:(eparlib.nic.in*)",
                fields=["identifier", "eparlib_document_url"],
            )
        assert len(results) == 1
        doc_url = results[0].get("eparlib_document_url", "")
        assert "archive.org" not in doc_url
        assert "eparlib.sansad.in" in doc_url
