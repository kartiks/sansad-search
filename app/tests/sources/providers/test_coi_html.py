"""Tests for ingest.sources.providers.coi_html — CoidHtmlProvider."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._http import RobotsChecker
from ingest.sources._provider import DocumentRef
from ingest.sources.providers.coi_html import (
    COI_BASE,
    CoidHtmlProvider,
    _default_day_filter,
    _default_volume_filter,
)

# ── Fixture HTML helpers ──────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _index_html() -> str:
    return (_FIXTURES / "coi_index.html").read_text()


def _volume_html() -> str:
    return (_FIXTURES / "coi_volume.html").read_text()


# ── URL filter unit tests ─────────────────────────────────────────────────────

class TestDefaultVolumeFilter:
    def test_volume_url_accepted(self):
        url = f"{COI_BASE}/debates/volume-1/"
        assert _default_volume_filter(url) is True

    def test_non_coi_url_rejected(self):
        assert _default_volume_filter("https://example.com/debates/volume-1/") is False

    def test_url_without_volume_rejected(self):
        assert _default_volume_filter(f"{COI_BASE}/debates/") is False

    def test_index_url_rejected(self):
        from ingest.sources.providers.coi_html import COI_INDEX_URL
        assert _default_volume_filter(COI_INDEX_URL) is False

    def test_volume_12_accepted(self):
        assert _default_volume_filter(f"{COI_BASE}/debates/volume-12/") is True


class TestDefaultDayFilter:
    def test_day_url_accepted(self):
        url = f"{COI_BASE}/debates/volume-1/1946-12-09/"
        assert _default_day_filter(url) is True

    def test_volume_url_rejected(self):
        # Volume URLs end with /volume-N/ — last segment contains "volume"
        url = f"{COI_BASE}/debates/volume-1/"
        assert _default_day_filter(url) is False

    def test_non_coi_url_rejected(self):
        assert _default_day_filter("https://example.com/debates/volume-1/1946-12-09/") is False

    def test_shallow_url_rejected(self):
        # Only 2 path parts — too shallow to be a day URL
        url = f"{COI_BASE}/debates/volume-1"
        # path parts after stripping base: ["debates", "volume-1"] → 2 parts < 3
        assert _default_day_filter(url) is False


# ── CoidHtmlProvider.discover() ───────────────────────────────────────────────

def _allow_all_robots():
    from urllib.robotparser import RobotFileParser
    p = RobotFileParser()
    p.allow_all = True
    return p


class TestCoidHtmlProviderDiscover:
    """Use fixture HTML to simulate index + volume page responses."""

    def _make_client_with_fixture_html(self, index_html: str, volume_html: str) -> AsyncMock:
        """
        Build an AsyncMock client that returns:
          - index_html for the first call (index page)
          - volume_html for subsequent calls (volume pages)
        """
        index_resp = MagicMock(status_code=200, text=index_html)
        volume_resp = MagicMock(status_code=200, text=volume_html)

        client = AsyncMock(spec=httpx.AsyncClient)
        # First call = index, remaining calls = volume pages
        client.get.side_effect = [index_resp] + [volume_resp] * 20
        return client

    async def test_discovers_12_volumes_from_fixture_index(self):
        """coi_index.html has 12 volume links; one volume page returns 3 day links."""
        index_html = _index_html()
        volume_html = _volume_html()
        client = self._make_client_with_fixture_html(index_html, volume_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client,
            rate_delay=0.0,
            robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()

        # 12 volumes × 3 day pages each = 36 DocumentRefs
        assert len(doc_refs) == 36

    async def test_doc_ref_has_correct_corpus_and_format(self):
        index_html = _index_html()
        volume_html = _volume_html()
        client = self._make_client_with_fixture_html(index_html, volume_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.corpus == "CA"
            assert ref.format == "html"
            assert ref.provider == "coi_html"

    async def test_canonical_doc_id_equals_citation_url_equals_fetch_url(self):
        """Day URL is the canonical_doc_id, citation_url, and fetch_url."""
        index_html = _index_html()
        volume_html = _volume_html()
        client = self._make_client_with_fixture_html(index_html, volume_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.canonical_doc_id == ref.fetch_url
            assert ref.canonical_doc_id == ref.citation_url
            assert ref.citation_url is not None
            assert "archive.org" not in ref.citation_url

    async def test_citation_url_is_never_archive_org(self):
        """citation_url must never be an archive.org URL (Non-Negotiable #9)."""
        index_html = _index_html()
        volume_html = _volume_html()
        client = self._make_client_with_fixture_html(index_html, volume_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()

        for ref in doc_refs:
            assert ref.citation_url is None or "archive.org" not in ref.citation_url

    async def test_volume_metadata_set_on_doc_refs(self):
        """Each DocumentRef carries the volume number in metadata."""
        index_html = _index_html()
        volume_html = _volume_html()
        client = self._make_client_with_fixture_html(index_html, volume_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()

        volumes = {ref.metadata["volume"] for ref in doc_refs}
        # 12 volumes indexed from 1
        assert volumes == set(range(1, 13))

    async def test_empty_index_returns_empty_list(self):
        empty_html = "<html><body>No volumes here.</body></html>"
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text=empty_html)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        doc_refs = await provider.discover()
        assert doc_refs == []

    async def test_duplicate_day_urls_deduplicated(self):
        """If the same day URL appears in two volume pages, only one DocumentRef is created."""
        shared_day = f"{COI_BASE}/debates/volume-1/1946-12-09/"
        index_html = f"""
        <html><body>
          <a href="{COI_BASE}/debates/volume-1/">Vol 1</a>
          <a href="{COI_BASE}/debates/volume-2/">Vol 2</a>
        </body></html>
        """
        volume_html = f"""
        <html><body>
          <a href="{shared_day}">9 Dec 1946</a>
        </body></html>
        """
        index_resp = MagicMock(status_code=200, text=index_html)
        vol_resp = MagicMock(status_code=200, text=volume_html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [index_resp, vol_resp, vol_resp]

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        def vol_filter(url):
            return COI_BASE in url and "volume" in url.lower()

        def day_filter(url):
            return COI_BASE in url and "1946-12-09" in url

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
            volume_url_filter=vol_filter,
            day_url_filter=day_filter,
        )
        doc_refs = await provider.discover()
        # Only 1 unique day URL, not 2
        assert len(doc_refs) == 1

    async def test_robots_disallowed_volume_skipped(self):
        """A volume URL disallowed by robots.txt produces no day DocumentRefs."""
        vol_url = f"{COI_BASE}/debates/volume-1/"
        index_html = f'<html><body><a href="{vol_url}">Vol 1</a></body></html>'
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text=index_html)

        from urllib.robotparser import RobotFileParser
        p = RobotFileParser()
        p.disallow_all = True
        robots = RobotsChecker()
        robots._cache[COI_BASE] = p

        def vol_filter(url):
            return "volume" in url.lower() and COI_BASE in url

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
            volume_url_filter=vol_filter,
        )
        doc_refs = await provider.discover()
        assert doc_refs == []

    async def test_index_fetch_failure_returns_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=500)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            doc_refs = await provider.discover()
        assert doc_refs == []


# ── CoidHtmlProvider.fetch() ──────────────────────────────────────────────────

class TestCoidHtmlProviderFetch:
    def _make_doc_ref(self, url: str = f"{COI_BASE}/debates/volume-1/1946-12-09/") -> DocumentRef:
        return DocumentRef(
            corpus="CA",
            provider="coi_html",
            format="html",
            fetch_url=url,
            canonical_doc_id=url,
            citation_url=url,
            metadata={"volume": 1},
        )

    async def test_fetch_returns_html_text(self):
        html = "<html><body>Debate text</body></html>"
        resp = MagicMock(status_code=200, text=html)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        result = await provider.fetch(self._make_doc_ref())
        assert isinstance(result, str)
        assert "Debate text" in result

    async def test_fetch_returns_none_on_http_failure(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=404)

        robots = RobotsChecker()
        robots._cache[COI_BASE] = _allow_all_robots()

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        result = await provider.fetch(self._make_doc_ref())
        assert result is None

    async def test_fetch_returns_none_when_robots_disallows(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = MagicMock(status_code=200, text="<html></html>")

        from urllib.robotparser import RobotFileParser
        p = RobotFileParser()
        p.disallow_all = True
        robots = RobotsChecker()
        robots._cache[COI_BASE] = p

        provider = CoidHtmlProvider(
            client, rate_delay=0.0, robots_checker=robots,
            index_url=f"{COI_BASE}/historical-constitution/debates",
        )
        result = await provider.fetch(self._make_doc_ref())
        assert result is None
