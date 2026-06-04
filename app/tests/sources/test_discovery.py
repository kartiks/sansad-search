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
    async def test_date_from_excludes_pre_scope_items(self):
        """Items with a date before date_from must be excluded from results."""
        html = """
        <html><body>
          <table>
            <tr>
              <td><a href="/handle/123456789/100">Old item 2013</a></td>
              <td>2013-06-01</td>
            </tr>
            <tr>
              <td><a href="/handle/123456789/200">New item 2015</a></td>
              <td>2015-03-01</td>
            </tr>
          </table>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_from="2014-01-01",
                rpp=20,
            )
        assert not any("/100" in u for u in urls), "pre-2014 item must be excluded"
        assert any("/200" in u for u in urls), "in-scope item must be included"

    @pytest.mark.asyncio
    async def test_date_from_none_returns_all_items(self):
        """When date_from is None all items are returned regardless of date."""
        html = """
        <html><body>
          <table>
            <tr>
              <td><a href="/handle/123456789/100">Old item</a></td>
              <td>2013-06-01</td>
            </tr>
          </table>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                rpp=20,
            )
        assert any("/100" in u for u in urls), "item must be included when date_from is None"

    @pytest.mark.asyncio
    async def test_no_date_in_row_included_failsafe(self):
        """Items with no parseable date in their row must be included (fail-safe)."""
        html = """
        <html><body>
          <table>
            <tr>
              <td><a href="/handle/123456789/999">No date</a></td>
            </tr>
          </table>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_from="2014-01-01",
                rpp=20,
            )
        assert any("/999" in u for u in urls), "item without date must be included (fail-safe)"

    @pytest.mark.asyncio
    async def test_pre_scope_items_do_not_stop_pagination(self):
        """Pre-scope items are filtered but still count toward the rpp stop criterion."""
        # Page 1: 2 items both pre-2014 — neither makes it to results,
        # but pagination should continue because found_on_page == rpp (2).
        html_page1 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/1">Item 1</a></td><td>2012-01-01</td></tr>
            <tr><td><a href="/handle/123456789/2">Item 2</a></td><td>2013-01-01</td></tr>
          </table>
        </body></html>
        """
        html_page2 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/3">Item 3</a></td><td>2015-01-01</td></tr>
          </table>
        </body></html>
        """
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_response(html_page1 if call_count == 1 else html_page2)

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_from="2014-01-01",
                rpp=2,
            )
        base = "https://eparlib.sansad.in/handle/123456789/"
        assert call_count == 2, "must paginate to second page even when page 1 is fully filtered"
        assert (base + "3") in urls, "in-scope item from page 2 must be collected"
        assert (base + "1") not in urls, "pre-2014 item 1 must be excluded"
        assert (base + "2") not in urls, "pre-2014 item 2 must be excluded"

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

    @pytest.mark.asyncio
    async def test_date_to_only_appends_upper_bound_to_query(self):
        """date_to alone appends AND date:[* TO {date_to}] to the Lucene query."""
        captured_url: list[str] = []

        async def fetch_mock(client_, url, **kwargs):
            captured_url.append(url)
            return _mock_json_response({"response": {"docs": []}})

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            await enumerate_ia_search(
                client, "identifier:(eparlib.nic.in*)", date_to="2024-03-31"
            )

        assert captured_url, "no request was made"
        assert "date:%5B*+TO+2024-03-31%5D" in captured_url[0] or "date:[* TO 2024-03-31]" in captured_url[0], (
            f"expected date_to in query, got URL: {captured_url[0]}"
        )

    @pytest.mark.asyncio
    async def test_date_from_and_date_to_combined_in_query(self):
        """Both date_from and date_to produce AND date:[{from} TO {to}] in the Lucene query."""
        captured_url: list[str] = []

        async def fetch_mock(client_, url, **kwargs):
            captured_url.append(url)
            return _mock_json_response({"response": {"docs": []}})

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            await enumerate_ia_search(
                client,
                "identifier:(eparlib.nic.in*)",
                date_from="2024-01-01",
                date_to="2024-03-31",
            )

        assert captured_url, "no request was made"
        url = captured_url[0]
        # The Lucene clause should use a closed range [from TO to], not open [from TO *]
        assert "TO+*" not in url and "TO *" not in url, (
            f"expected closed range, but got open range in URL: {url}"
        )
        assert "2024-01-01" in url and "2024-03-31" in url, (
            f"expected both dates in query URL: {url}"
        )

    @pytest.mark.asyncio
    async def test_date_to_excludes_items_past_bound(self):
        """paginate_dspace_browse with date_to must exclude items dated after the bound."""
        html = """
        <html><body>
          <table>
            <tr>
              <td><a href="/handle/123456789/100">Item Jan 2024</a></td>
              <td>2024-01-15</td>
            </tr>
            <tr>
              <td><a href="/handle/123456789/200">Item May 2024</a></td>
              <td>2024-05-20</td>
            </tr>
          </table>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry",
                       AsyncMock(return_value=_mock_response(html)))
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_to="2024-03-31",
                rpp=20,
            )
        assert any("/100" in u for u in urls), "in-scope Jan item must be included"
        assert not any("/200" in u for u in urls), "May item past date_to must be excluded"

    @pytest.mark.asyncio
    async def test_date_to_pagination_breaks_early_when_all_items_past_bound(self):
        """When every item on a page exceeds date_to, pagination stops without fetching more pages."""
        # All items on the page are past date_to=2024-03-31
        html_page1 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/10">Item A</a></td><td>2024-05-01</td></tr>
            <tr><td><a href="/handle/123456789/11">Item B</a></td><td>2024-06-01</td></tr>
          </table>
        </body></html>
        """
        html_page2 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/20">Item C</a></td><td>2024-07-01</td></tr>
            <tr><td><a href="/handle/123456789/21">Item D</a></td><td>2024-08-01</td></tr>
          </table>
        </body></html>
        """
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_response(html_page1 if call_count == 1 else html_page2)

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_to="2024-03-31",
                rpp=2,
            )

        assert call_count == 1, "should stop after first page when all items exceed date_to"
        assert urls == [], "no items should be returned when all are past date_to"

    @pytest.mark.asyncio
    async def test_date_to_does_not_break_early_when_page_has_mixed_dates(self):
        """Pagination continues when a page has both in-scope and post-scope items."""
        html_page1 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/1">In scope</a></td><td>2024-02-01</td></tr>
            <tr><td><a href="/handle/123456789/2">Post scope</a></td><td>2024-05-01</td></tr>
          </table>
        </body></html>
        """
        # Page 2 returns fewer than rpp items, triggering normal stop
        html_page2 = """
        <html><body>
          <table>
            <tr><td><a href="/handle/123456789/3">Also in scope</a></td><td>2024-03-01</td></tr>
          </table>
        </body></html>
        """
        call_count = 0

        async def fetch_mock(client_, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_response(html_page1 if call_count == 1 else html_page2)

        client = AsyncMock(spec=httpx.AsyncClient)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("ingest.sources._discovery.fetch_with_retry", fetch_mock)
            urls = await paginate_dspace_browse(
                client,
                "https://eparlib.sansad.in/browse",
                date_to="2024-03-31",
                rpp=2,
            )

        assert call_count == 2, "should continue paginating when page has mixed dates"
        assert any("/1" in u for u in urls), "in-scope item must be included"
        assert not any("/2" in u for u in urls), "post-scope item must be excluded"
        assert any("/3" in u for u in urls), "page 2 in-scope item must be included"
