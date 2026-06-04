"""Tests for ingest.sources.providers.sansad_rs_html — SansadRsHtmlProvider."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._http import RobotsChecker
from ingest.sources._provider import DocumentRef
from ingest.sources.providers.sansad_rs_html import (
    SANSAD_BASE,
    SANSAD_RS_LISTING_URL,
    SansadRsHtmlProvider,
    _date_from_url,
    _default_sitting_filter,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _listing_html() -> str:
    return (_FIXTURES / "sansad_rs_listing.html").read_text()


def _allow_all_robots() -> RobotsChecker:
    rc = RobotsChecker()
    rc.is_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return rc


# ── Constant ──────────────────────────────────────────────────────────────────

class TestListingUrl:
    def test_listing_url_targets_rs_debates_officials(self):
        assert SANSAD_RS_LISTING_URL == "https://sansad.in/rs/debates/officials"


# ── _date_from_url ────────────────────────────────────────────────────────────

class TestDateFromUrl:
    def test_extracts_date_with_slash_separators(self):
        assert _date_from_url("https://sansad.in/rs/debates/officials/2023/03/15") == date(2023, 3, 15)

    def test_extracts_date_with_dash_separators(self):
        assert _date_from_url("https://sansad.in/rs/debates/2023-03-15") == date(2023, 3, 15)

    def test_returns_none_when_no_date(self):
        assert _date_from_url("https://sansad.in/rs/debates/officials") is None

    def test_returns_none_for_invalid_date(self):
        assert _date_from_url("https://sansad.in/rs/debates/2023/13/40") is None


# ── _default_sitting_filter ───────────────────────────────────────────────────

class TestDefaultSittingFilter:
    def test_accepts_sitting_page(self):
        assert _default_sitting_filter("https://sansad.in/rs/debates/officials/2023/03/15") is True

    def test_rejects_listing_root(self):
        assert _default_sitting_filter("https://sansad.in/rs/debates/officials") is False

    def test_rejects_external_host(self):
        assert _default_sitting_filter("https://example.com/rs/debates/officials/2023/03/15") is False

    def test_rejects_unrelated_sansad_path(self):
        assert _default_sitting_filter("https://sansad.in/ls/business") is False


# ── discover() ────────────────────────────────────────────────────────────────

class TestSansadRsHtmlDiscover:
    async def test_discovers_in_scope_sittings_from_fixture(self):
        """Fixture lists 3 sittings; the 2013 sitting is excluded (pre-2014)."""
        listing_resp = MagicMock(status_code=200, text=_listing_html())
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        # 2023-03-15 and 2022-07-10 are in scope; 2013-12-20 is excluded.
        dates = {ref.metadata["sitting_date"] for ref in doc_refs}
        assert "2023-03-15" in dates
        assert "2022-07-10" in dates
        assert "2013-12-20" not in dates
        assert len(doc_refs) == 2

    async def test_doc_ref_corpus_format_and_provider(self):
        listing_resp = MagicMock(status_code=200, text=_listing_html())
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        assert len(doc_refs) >= 1
        for ref in doc_refs:
            assert ref.corpus == "RS"
            assert ref.format == "html"
            assert ref.provider == "sansad_rs_html"

    async def test_canonical_doc_id_and_citation_url_are_page_url(self):
        """sansad.in/rs has no DSpace handle — page URL is its own identity + citation."""
        listing_resp = MagicMock(status_code=200, text=_listing_html())
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.canonical_doc_id == ref.fetch_url
            assert ref.citation_url == ref.fetch_url
            assert SANSAD_BASE in ref.fetch_url
            assert "archive.org" not in ref.fetch_url

    async def test_listing_root_link_excluded(self):
        """The listing root (/rs/debates/officials) must not appear as a sitting."""
        listing_resp = MagicMock(status_code=200, text=_listing_html())
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.fetch_url.rstrip("/") != SANSAD_RS_LISTING_URL.rstrip("/")

    async def test_returns_empty_when_listing_unfetchable(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=404)

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = SansadRsHtmlProvider(
                client, rate_delay=0.0, robots_checker=_allow_all_robots()
            )
            doc_refs = await provider.discover()

        assert doc_refs == []


# ── fetch() ───────────────────────────────────────────────────────────────────

class TestSansadRsHtmlFetch:
    def _make_doc_ref(self) -> DocumentRef:
        url = "https://sansad.in/rs/debates/officials/2023/03/15"
        return DocumentRef(
            corpus="RS",
            provider="sansad_rs_html",
            format="html",
            fetch_url=url,
            canonical_doc_id=url,
            citation_url=url,
            metadata={"sitting_date": "2023-03-15"},
        )

    async def test_fetch_returns_html_text(self):
        html = "<html><body><h1>Rajya Sabha Debate</h1></body></html>"
        resp = MagicMock(status_code=200, text=html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        result = await provider.fetch(self._make_doc_ref())

        assert isinstance(result, str)
        assert "Rajya Sabha Debate" in result

    async def test_fetch_skips_when_robots_disallows(self):
        rc = RobotsChecker()
        rc.is_allowed = AsyncMock(return_value=False)  # type: ignore[method-assign]
        client = AsyncMock(spec=httpx.AsyncClient)

        provider = SansadRsHtmlProvider(client, rate_delay=0.0, robots_checker=rc)
        result = await provider.fetch(self._make_doc_ref())

        assert result is None
        client.get.assert_not_called()

    async def test_fetch_returns_none_on_http_failure(self):
        resp = MagicMock(status_code=503)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp

        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            provider = SansadRsHtmlProvider(
                client, rate_delay=0.0, robots_checker=_allow_all_robots()
            )
            result = await provider.fetch(self._make_doc_ref())

        assert result is None


# ── Date boundary (Gap 4) ─────────────────────────────────────────────────────

class TestDateBoundary:
    """Gap 4: exact boundary day 2014-01-01 retained; 2013-12-31 excluded."""

    def test_boundary_date_2014_01_01_extracted(self):
        url = "https://sansad.in/rs/debates/officials/2014/01/01"
        assert _date_from_url(url) == date(2014, 1, 1)

    def test_pre_boundary_date_2013_12_31_extracted(self):
        url = "https://sansad.in/rs/debates/officials/2013/12/31"
        assert _date_from_url(url) == date(2013, 12, 31)

    async def test_discover_includes_2014_01_01_and_excludes_2013_12_31(self):
        """discover() retains the exact boundary date and excludes the day before."""
        boundary_html = (
            "<!DOCTYPE html><html><body>"
            '<a href="/rs/debates/officials/2014/01/01">Sitting 2014-01-01</a>'
            '<a href="/rs/debates/officials/2013/12/31">Sitting 2013-12-31</a>'
            "</body></html>"
        )
        listing_resp = MagicMock(status_code=200, text=boundary_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        dates = {ref.metadata["sitting_date"] for ref in doc_refs}
        assert "2014-01-01" in dates
        assert "2013-12-31" not in dates
        assert len(doc_refs) == 1


class TestDateToFilter:
    """date_to constructor param excludes sittings dated after the upper bound."""

    async def test_date_to_excludes_urls_past_bound(self):
        """discover() with date_to excludes sitting URLs dated after the bound."""
        html = (
            "<!DOCTYPE html><html><body>"
            '<a href="/rs/debates/officials/2024/02/15">Feb 2024</a>'
            '<a href="/rs/debates/officials/2024/05/20">May 2024</a>'
            "</body></html>"
        )
        listing_resp = MagicMock(status_code=200, text=html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots(),
            date_to="2024-03-31",
        )
        doc_refs = await provider.discover()

        dates = {ref.metadata["sitting_date"] for ref in doc_refs}
        assert "2024-02-15" in dates, "Feb sitting (before date_to) must be included"
        assert "2024-05-20" not in dates, "May sitting (after date_to) must be excluded"

    async def test_date_to_stored_as_date_object(self):
        """date_to is stored as a datetime.date internally."""
        client = AsyncMock(spec=httpx.AsyncClient)
        provider = SansadRsHtmlProvider(client, date_to="2024-03-31")
        assert provider._date_to == date(2024, 3, 31)

    async def test_no_date_to_includes_all_in_scope_urls(self):
        """Without date_to, all in-scope (post-2014) URLs are included."""
        html = (
            "<!DOCTYPE html><html><body>"
            '<a href="/rs/debates/officials/2024/02/15">Feb 2024</a>'
            '<a href="/rs/debates/officials/2025/10/01">Oct 2025</a>'
            "</body></html>"
        )
        listing_resp = MagicMock(status_code=200, text=html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = listing_resp

        provider = SansadRsHtmlProvider(
            client, rate_delay=0.0, robots_checker=_allow_all_robots()
        )
        doc_refs = await provider.discover()

        dates = {ref.metadata["sitting_date"] for ref in doc_refs}
        assert "2024-02-15" in dates
        assert "2025-10-01" in dates
