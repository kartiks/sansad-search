"""
Shared HTTP utilities for ingestion source fetchers.

Handles per-F01 spec:
  - 4xx (excl. 429) → log warning, return None (caller skips the document)
  - 5xx → exponential backoff, retry up to MAX_RETRIES_5XX, then return None
  - 429 → exponential backoff, retry indefinitely (never skip)
  - Network error → log error, return None

Rate limiting (inter-request delay) is the caller's responsibility; this
module handles only retries and robots.txt compliance.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "SansadSearch-Ingest/1.0"
DEFAULT_RATE_DELAY: float = 1.0   # seconds between successive document fetches
MAX_RETRIES_5XX: int = 3
INITIAL_BACKOFF: float = 2.0      # seconds; doubles on each retry


class RobotsChecker:
    """Fetches robots.txt once per domain and caches the result."""

    def __init__(self) -> None:
        self._cache: dict[str, RobotFileParser] = {}

    async def is_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """Return True if USER_AGENT is permitted to fetch *url* per robots.txt."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            robots_url = f"{base}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                resp = await client.get(robots_url, follow_redirects=True)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    parser.allow_all = True
            except Exception as exc:
                logger.warning("Could not fetch robots.txt from %s: %s", base, exc)
                parser.allow_all = True
            self._cache[base] = parser
        return self._cache[base].can_fetch(USER_AGENT, url)


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries_5xx: int = MAX_RETRIES_5XX,
    initial_backoff: float = INITIAL_BACKOFF,
) -> Optional[httpx.Response]:
    """
    GET *url* with error handling per F01 spec.

    Returns the httpx.Response on HTTP 200, None when the document should be
    skipped (4xx other than 429 or exhausted 5xx retries).

    The caller is responsible for applying inter-request rate delay *before*
    calling this function (or after a successful return).
    """
    backoff = initial_backoff
    retries_5xx = 0

    while True:
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.RequestError as exc:
            logger.error("Request error fetching %s: %s", url, exc)
            return None

        if resp.status_code == 200:
            return resp

        if resp.status_code == 429:
            logger.warning(
                "429 rate-limited on %s; backing off %.1f s", url, backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120.0)
            continue

        if 500 <= resp.status_code < 600:
            if retries_5xx < max_retries_5xx:
                logger.warning(
                    "HTTP %d on %s; retry %d/%d in %.1f s",
                    resp.status_code, url, retries_5xx + 1, max_retries_5xx, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120.0)
                retries_5xx += 1
                continue
            logger.error(
                "HTTP %d on %s after %d retries; skipping",
                resp.status_code, url, max_retries_5xx,
            )
            return None

        # All other 4xx (excludes 429 handled above)
        logger.warning("HTTP %d on %s; skipping", resp.status_code, url)
        return None
