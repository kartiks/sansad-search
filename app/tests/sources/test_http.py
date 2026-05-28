"""Tests for ingest.sources._http — retry logic and robots.txt compliance."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._http import RobotsChecker, fetch_with_retry


# ── fetch_with_retry ──────────────────────────────────────────────────────────

class TestFetchWithRetry:
    @pytest.mark.asyncio
    async def test_200_returns_response(self):
        resp = MagicMock(status_code=200)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp
        result = await fetch_with_retry(client, "http://example.com/doc.html")
        assert result is resp

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        resp = MagicMock(status_code=404)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp
        result = await fetch_with_retry(client, "http://example.com/missing.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_403_returns_none(self):
        resp = MagicMock(status_code=403)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp
        result = await fetch_with_retry(client, "http://example.com/forbidden.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_5xx_retries_up_to_max_then_returns_none(self):
        resp = MagicMock(status_code=503)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_with_retry(
                client,
                "http://example.com/flaky.html",
                max_retries_5xx=3,
                initial_backoff=0.0,
            )
        assert result is None
        # Called once + 3 retries = 4 total
        assert client.get.call_count == 4

    @pytest.mark.asyncio
    async def test_5xx_succeeds_on_retry(self):
        """5xx followed by 200 → returns the 200 response."""
        bad = MagicMock(status_code=500)
        good = MagicMock(status_code=200)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [bad, good]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_with_retry(
                client, "http://example.com/doc.html", initial_backoff=0.0
            )
        assert result is good

    @pytest.mark.asyncio
    async def test_429_retries_and_eventually_succeeds(self):
        """429 → retry indefinitely; must not skip."""
        rate_limited = MagicMock(status_code=429)
        ok = MagicMock(status_code=200)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [rate_limited, rate_limited, ok]
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_with_retry(
                client, "http://example.com/doc.html", initial_backoff=0.0
            )
        assert result is ok
        assert client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_request_error_returns_none(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.RequestError("connection refused")
        result = await fetch_with_retry(client, "http://example.com/doc.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_429_never_skipped(self):
        """429 must never cause a skip — verify retry count > max_retries_5xx."""
        responses = [MagicMock(status_code=429)] * 5 + [MagicMock(status_code=200)]
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = responses
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_with_retry(
                client, "http://example.com/doc.html",
                max_retries_5xx=3, initial_backoff=0.0
            )
        assert result is not None
        assert result.status_code == 200


# ── RobotsChecker ─────────────────────────────────────────────────────────────

class TestRobotsChecker:
    @pytest.mark.asyncio
    async def test_allowed_when_no_disallow_rule(self):
        robots_text = "User-agent: *\nAllow: /"
        resp_robots = MagicMock(status_code=200, text=robots_text)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp_robots

        checker = RobotsChecker()
        allowed = await checker.is_allowed(client, "http://example.com/some/path")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_disallowed_url_returns_false(self):
        robots_text = "User-agent: *\nDisallow: /private/"
        resp_robots = MagicMock(status_code=200, text=robots_text)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp_robots

        checker = RobotsChecker()
        allowed = await checker.is_allowed(client, "http://example.com/private/secret.pdf")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_robots_txt_404_allows_all(self):
        """If robots.txt is not found (404), all paths are allowed."""
        resp_robots = MagicMock(status_code=404)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp_robots

        checker = RobotsChecker()
        allowed = await checker.is_allowed(client, "http://example.com/any/path")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_cached_per_domain(self):
        """robots.txt is fetched once per domain, not per URL."""
        robots_text = "User-agent: *\nAllow: /"
        resp = MagicMock(status_code=200, text=robots_text)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = resp

        checker = RobotsChecker()
        await checker.is_allowed(client, "http://example.com/page1")
        await checker.is_allowed(client, "http://example.com/page2")
        # robots.txt fetch is the first call; page fetches are done by the source
        # The checker calls client.get exactly once (for robots.txt)
        assert client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_network_error_on_robots_allows_all(self):
        """If robots.txt fetch fails with a network error, all paths are allowed."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.RequestError("timeout")

        checker = RobotsChecker()
        allowed = await checker.is_allowed(client, "http://example.com/doc.html")
        assert allowed is True
