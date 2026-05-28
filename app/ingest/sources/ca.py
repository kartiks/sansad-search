"""
Constituent Assembly source: enumerates and fetches all 12 CA debate PDF volumes.

All 12 volume URLs are fixed and well-known (sansad.in Lok Sabha archives).
No dynamic URL discovery is needed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

import httpx

from ingest.sources._http import (
    DEFAULT_RATE_DELAY,
    RobotsChecker,
    fetch_with_retry,
)

logger = logging.getLogger(__name__)

# Base URL for CA PDF volumes on sansad.in
CA_VOLUME_BASE = "https://sansad.in/getFile/constitutiondebates"

# All 12 Constituent Assembly Debates volumes (fixed, no discovery needed)
CA_VOLUME_URLS: list[str] = [
    f"{CA_VOLUME_BASE}/Volume_{i:02d}.pdf" for i in range(1, 13)
]


class CASource:
    """
    Fetches all 12 Constituent Assembly debate PDF volumes from sansad.in.

    Usage (async context):
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            source = CASource(rate_delay=1.0)
            async for url, content, meta in source.fetch_documents(client):
                # content is bytes (PDF)
                # meta = {"source": "CA", "volume": N}
                ...
    """

    def __init__(
        self,
        rate_delay: float = DEFAULT_RATE_DELAY,
        robots_checker: Optional[RobotsChecker] = None,
        volume_urls: Optional[list[str]] = None,
    ) -> None:
        self.rate_delay = rate_delay
        self.robots_checker = robots_checker or RobotsChecker()
        self._volume_urls = volume_urls if volume_urls is not None else CA_VOLUME_URLS

    def enumerate_urls(self) -> list[str]:
        """Return the ordered list of CA volume PDF URLs (12 items)."""
        return list(self._volume_urls)

    async def fetch_documents(
        self,
        client: httpx.AsyncClient,
    ) -> AsyncGenerator[tuple[str, bytes, dict], None]:
        """
        Async generator yielding (url, content_bytes, metadata) for each volume.

        Skips volumes disallowed by robots.txt or where the HTTP response
        indicates the document should be skipped (4xx, exhausted 5xx retries).
        Yields nothing for skipped volumes so the caller can count skips separately.
        """
        for i, url in enumerate(self.enumerate_urls(), start=1):
            if not await self.robots_checker.is_allowed(client, url):
                logger.warning("robots.txt disallows %s; skipping", url)
                continue

            resp = await fetch_with_retry(client, url)
            if resp is None:
                logger.warning("Skipping CA volume %d (%s)", i, url)
                continue

            yield url, resp.content, {"source": "CA", "volume": i}

            if self.rate_delay > 0:
                await asyncio.sleep(self.rate_delay)
