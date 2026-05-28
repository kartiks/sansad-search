"""Tests for ingest.sources.ls and ingest.sources.rs — URL discovery and fetching."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.sources._http import RobotsChecker
from ingest.sources.ls import LSSource, _infer_proceeding_type, _sitting_key, _date_from_url
from ingest.sources.rs import RSSource


# ── LS helper functions ───────────────────────────────────────────────────────

class TestLSHelpers:
    def test_infer_proceeding_type_starred(self):
        assert _infer_proceeding_type("https://sansad.in/starredquestion/2023") == "starred_question"

    def test_infer_proceeding_type_unstarred(self):
        assert _infer_proceeding_type("https://sansad.in/unstarredquestion/2023") == "unstarred_question"

    def test_infer_proceeding_type_unstarred_before_starred(self):
        """unstarred_question fragment must be checked before starred_question."""
        url = "https://sansad.in/unstarredquestion/abc"
        result = _infer_proceeding_type(url)
        assert result == "unstarred_question"

    def test_infer_proceeding_type_zero_hour(self):
        assert _infer_proceeding_type("https://sansad.in/zerohour/2023") == "zero_hour"

    def test_infer_proceeding_type_unknown_returns_none(self):
        assert _infer_proceeding_type("https://sansad.in/unknown/path") is None

    def test_date_from_url_extracts_date(self):
        d = _date_from_url("https://sansad.in/ls/2023/03/15/debate.html")
        assert d == date(2023, 3, 15)

    def test_date_from_url_returns_none_if_no_date(self):
        assert _date_from_url("https://sansad.in/ls/index.html") is None

    def test_sitting_key_strips_extension(self):
        html_key = _sitting_key("https://sansad.in/doc.html")
        pdf_key = _sitting_key("https://sansad.in/doc.pdf")
        assert html_key == pdf_key


class TestLSSourceDiscovery:
    @pytest.mark.asyncio
    async def test_discover_returns_html_over_pdf_for_same_sitting(self):
        """When HTML and PDF exist for the same sitting, only the HTML URL is returned."""
        index_html = """
        <html><body>
          <a href="/ls/2023/03/15/debate.html">Debate HTML</a>
          <a href="/ls/2023/03/15/debate.pdf">Debate PDF</a>
        </body></html>
        """
        index_resp = MagicMock(status_code=200, text=index_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = index_resp

        source = LSSource(
            rate_delay=0.0,
            date_from=date(2014, 1, 1),
            index_url="https://sansad.in/ls/index",
        )
        urls = await source.discover_document_urls(client)
        hrefs = [u for u, _ in urls]
        # HTML preferred over PDF
        html_urls = [u for u in hrefs if "html" in u.lower()]
        pdf_urls = [u for u in hrefs if u.endswith(".pdf")]
        assert len(html_urls) >= 1
        assert len(pdf_urls) == 0

    @pytest.mark.asyncio
    async def test_discover_excludes_pre_2014_urls(self):
        """URLs with dates before 2014-01-01 must be excluded."""
        index_html = """
        <html><body>
          <a href="/ls/2013/12/31/debate.html">Old debate</a>
          <a href="/ls/2014/01/01/debate.html">New debate</a>
        </body></html>
        """
        index_resp = MagicMock(status_code=200, text=index_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = index_resp

        source = LSSource(
            rate_delay=0.0,
            date_from=date(2014, 1, 1),
            index_url="https://sansad.in/ls/index",
        )
        urls = await source.discover_document_urls(client)
        hrefs = [u for u, _ in urls]
        assert not any("2013" in u for u in hrefs)
        assert any("2014" in u for u in hrefs)

    @pytest.mark.asyncio
    async def test_discover_returns_empty_on_index_fetch_failure(self):
        """If the index page fails to fetch, returns empty list."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=500)

        source = LSSource(rate_delay=0.0, index_url="https://sansad.in/ls/index")
        urls = await source.discover_document_urls(client)
        assert urls == []

    @pytest.mark.asyncio
    async def test_date_exactly_2014_01_01_included(self):
        """Records dated exactly 2014-01-01 are in scope."""
        index_html = '<html><body><a href="/ls/2014/01/01/debate.html">Scope</a></body></html>'
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text=index_html)

        source = LSSource(
            rate_delay=0.0,
            date_from=date(2014, 1, 1),
            index_url="https://sansad.in/ls/index",
        )
        urls = await source.discover_document_urls(client)
        assert len(urls) == 1

    @pytest.mark.asyncio
    async def test_date_2013_12_31_excluded(self):
        """Records dated 2013-12-31 are out of scope."""
        index_html = '<html><body><a href="/ls/2013/12/31/debate.html">Old</a></body></html>'
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text=index_html)

        source = LSSource(
            rate_delay=0.0,
            date_from=date(2014, 1, 1),
            index_url="https://sansad.in/ls/index",
        )
        urls = await source.discover_document_urls(client)
        assert len(urls) == 0


class TestLSSourceFetch:
    @pytest.mark.asyncio
    async def test_fetch_skips_robots_disallowed(self):
        """URLs disallowed by robots.txt produce no yielded items."""
        index_html = '<html><body><a href="/ls/2023/01/10/debate.html">Doc</a></body></html>'
        index_resp = MagicMock(status_code=200, text=index_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = index_resp

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _disallow_all_parser()

        source = LSSource(
            rate_delay=0.0,
            robots_checker=robots,
            index_url="https://sansad.in/ls/index",
        )
        results = []
        async for item in source.fetch_documents(client):
            results.append(item)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fetch_html_content_is_str(self):
        index_html = '<html><body><a href="/ls/2023/01/10/debate.html">Doc</a></body></html>'
        doc_html = "<html><body>Some debate text</body></html>"
        index_resp = MagicMock(status_code=200, text=index_html)
        doc_resp = MagicMock(status_code=200, text=doc_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [index_resp, doc_resp]

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = LSSource(
            rate_delay=0.0,
            robots_checker=robots,
            index_url="https://sansad.in/ls/index",
        )
        results = []
        async for url, content, meta in source.fetch_documents(client):
            results.append((url, content, meta))

        assert len(results) == 1
        assert isinstance(results[0][1], str)
        assert results[0][2]["source"] == "LS"

    @pytest.mark.asyncio
    async def test_fetch_pdf_content_is_bytes(self):
        index_html = '<html><body><a href="/ls/2023/01/10/debate.pdf">Doc</a></body></html>'
        doc_bytes = b"%PDF-1.4 content"
        index_resp = MagicMock(status_code=200, text=index_html)
        doc_resp = MagicMock(status_code=200, content=doc_bytes)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [index_resp, doc_resp]

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = LSSource(
            rate_delay=0.0,
            robots_checker=robots,
            index_url="https://sansad.in/ls/index",
        )
        results = []
        async for url, content, meta in source.fetch_documents(client):
            results.append((url, content, meta))

        assert len(results) == 1
        assert isinstance(results[0][1], bytes)


class TestRSSource:
    @pytest.mark.asyncio
    async def test_rs_source_returns_rs_metadata(self):
        index_html = '<html><body><a href="/rsnew/2023/01/10/starred.html">Doc</a></body></html>'
        doc_html = "<html><body>RS debate text</body></html>"
        index_resp = MagicMock(status_code=200, text=index_html)
        doc_resp = MagicMock(status_code=200, text=doc_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [index_resp, doc_resp]

        robots = RobotsChecker()
        robots._cache["https://rajyasabha.gov.in"] = _allow_all_parser()

        source = RSSource(
            rate_delay=0.0,
            robots_checker=robots,
            index_url="https://rajyasabha.gov.in/rsnew/index",
        )
        results = []
        async for url, content, meta in source.fetch_documents(client):
            results.append(meta)

        assert all(m["source"] == "RS" for m in results)

    @pytest.mark.asyncio
    async def test_rs_source_html_preferred_over_pdf(self):
        index_html = """
        <html><body>
          <a href="/rsnew/2023/03/15/debate.html">HTML</a>
          <a href="/rsnew/2023/03/15/debate.pdf">PDF</a>
        </body></html>
        """
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text=index_html)

        source = RSSource(
            rate_delay=0.0,
            date_from=date(2014, 1, 1),
            index_url="https://rajyasabha.gov.in/index",
        )
        urls = await source.discover_document_urls(client)
        hrefs = [u for u, _ in urls]
        assert all(not u.endswith(".pdf") for u in hrefs)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _allow_all_parser():
    from urllib.robotparser import RobotFileParser
    p = RobotFileParser()
    p.allow_all = True
    return p


def _disallow_all_parser():
    from urllib.robotparser import RobotFileParser
    p = RobotFileParser()
    p.disallow_all = True
    return p
