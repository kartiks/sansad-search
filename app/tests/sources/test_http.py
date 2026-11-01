"""Tests for ingest.sources._http — retry logic and robots.txt compliance."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest.sources._http import RateLimiter, RobotsChecker, fetch_with_retry


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
    async def test_request_error_retried_then_returns_none(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.RequestError("connection refused")
        result = await fetch_with_retry(
            client, "http://example.com/doc.html", max_retries_5xx=3, initial_backoff=0
        )
        assert result is None
        assert client.get.call_count == 4

    async def test_timeout_then_success(self):
        ok = MagicMock(spec=httpx.Response)
        ok.status_code = 200
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [httpx.ReadTimeout("slow"), ok]
        result = await fetch_with_retry(client, "http://example.com/doc.html", initial_backoff=0)
        assert result is ok

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


# ── RateLimiter ───────────────────────────────────────────────────────────────


class TestRateLimiter:
    """Request starts are spaced by the interval; response time counts towards it."""

    async def _run(self, clock_steps, interval=1.0):
        clock = iter(clock_steps)
        sleeps = []
        limiter = RateLimiter(interval)
        with patch("ingest.sources._http.time.monotonic", side_effect=lambda: next(clock)), \
             patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock) as sleep:
            for _ in clock_steps:
                await limiter.wait()
            sleeps = [round(c.args[0], 3) for c in sleep.await_args_list]
        return sleeps

    @pytest.mark.asyncio
    async def test_first_request_does_not_wait(self):
        assert await self._run([100.0]) == []

    @pytest.mark.asyncio
    async def test_slow_responses_need_no_extra_wait(self):
        # each response took longer than the interval: no sleeping at all
        assert await self._run([100.0, 101.2, 102.5]) == []

    @pytest.mark.asyncio
    async def test_fast_responses_wait_out_the_rest_of_the_interval(self):
        # second call 0.3 s after the first start → sleep 0.7 s
        assert await self._run([100.0, 100.3]) == [0.7]

    @pytest.mark.asyncio
    async def test_back_to_back_callers_queue_behind_each_other(self):
        # three calls at the same instant get slots 0, +1 s, +2 s
        assert await self._run([100.0, 100.0, 100.0]) == [1.0, 2.0]

    @pytest.mark.asyncio
    async def test_zero_interval_never_waits(self):
        assert await self._run([1.0, 1.0], interval=0.0) == []

    @pytest.mark.asyncio
    async def test_fetch_with_retry_waits_before_every_attempt(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = [MagicMock(status_code=503), MagicMock(status_code=200)]
        limiter = AsyncMock(spec=RateLimiter)
        with patch("ingest.sources._http.asyncio.sleep", new_callable=AsyncMock):
            result = await fetch_with_retry(client, "http://example.com/doc.html", limiter=limiter)
        assert result.status_code == 200
        assert limiter.wait.await_count == 2
