"""Tests for ingest.sources.ca — CA volume URL enumeration and fetching."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ingest.sources._http import RobotsChecker
from ingest.sources.ca import CA_VOLUME_URLS, CASource


class TestCASourceEnumerate:
    def test_enumerate_urls_returns_12_items(self):
        source = CASource()
        urls = source.enumerate_urls()
        assert len(urls) == 12

    def test_enumerate_urls_are_https_pdfs(self):
        source = CASource()
        for url in CASource().enumerate_urls():
            assert url.startswith("https://")
            assert url.endswith(".pdf")

    def test_enumerate_urls_are_unique(self):
        source = CASource()
        urls = source.enumerate_urls()
        assert len(set(urls)) == 12

    def test_custom_volume_urls_respected(self):
        custom = ["https://example.com/vol1.pdf", "https://example.com/vol2.pdf"]
        source = CASource(volume_urls=custom)
        assert source.enumerate_urls() == custom


class TestCASourceFetch:
    @pytest.mark.asyncio
    async def test_fetch_documents_yields_all_12_volumes(self):
        """With all 12 URLs returning 200, yields exactly 12 items."""
        pdf_bytes = b"%PDF-1.4 mock pdf content"
        mock_resp = MagicMock(status_code=200, content=pdf_bytes)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        # Robots checker that always allows
        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = CASource(rate_delay=0.0, robots_checker=robots)
        results = []
        async for url, content, meta in source.fetch_documents(client):
            results.append((url, content, meta))

        assert len(results) == 12

    @pytest.mark.asyncio
    async def test_fetch_documents_metadata_has_source_ca_and_volume(self):
        pdf_bytes = b"%PDF mock"
        mock_resp = MagicMock(status_code=200, content=pdf_bytes)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = CASource(rate_delay=0.0, robots_checker=robots, volume_urls=CA_VOLUME_URLS[:3])
        results = []
        async for _, content, meta in source.fetch_documents(client):
            results.append(meta)

        assert all(m["source"] == "CA" for m in results)
        volumes = [m["volume"] for m in results]
        assert volumes == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_fetch_documents_skips_disallowed_by_robots(self):
        """Volumes disallowed by robots.txt are skipped."""
        pdf_bytes = b"%PDF mock"
        mock_resp = MagicMock(status_code=200, content=pdf_bytes)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        # Robots checker that never allows
        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _disallow_all_parser()

        source = CASource(
            rate_delay=0.0,
            robots_checker=robots,
            volume_urls=CA_VOLUME_URLS[:3],
        )
        results = []
        async for item in source.fetch_documents(client):
            results.append(item)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fetch_documents_skips_404_volume(self):
        """404 responses are skipped without raising."""
        missing = MagicMock(status_code=404)
        ok = MagicMock(status_code=200, content=b"%PDF ok")
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [missing, ok, ok]

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = CASource(
            rate_delay=0.0,
            robots_checker=robots,
            volume_urls=CA_VOLUME_URLS[:3],
        )
        results = []
        async for item in source.fetch_documents(client):
            results.append(item)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_content_is_bytes(self):
        pdf_bytes = b"%PDF-1.4 content"
        mock_resp = MagicMock(status_code=200, content=pdf_bytes)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = mock_resp

        robots = RobotsChecker()
        robots._cache["https://sansad.in"] = _allow_all_parser()

        source = CASource(
            rate_delay=0.0,
            robots_checker=robots,
            volume_urls=[CA_VOLUME_URLS[0]],
        )
        async for _, content, _ in source.fetch_documents(client):
            assert isinstance(content, bytes)


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
