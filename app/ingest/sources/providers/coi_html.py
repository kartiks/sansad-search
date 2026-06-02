"""
constitutionofindia.net CA provider.

Three-level discovery:
  1. Fetch the volume index page to get 12 volume-level URLs.
  2. For each volume, crawl the volume page to collect per-sitting (per-day) URLs.
  3. Return one DocumentRef per sitting page.

canonical_doc_id: the per-day page URL (single provider, URL is its own identity key
per DATA-MODELS §4.3).

citation_url: the same per-day page URL (appears as source_url in indexed records).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

import httpx

from ingest.sources._discovery import crawl_html_listing
from ingest.sources._http import DEFAULT_RATE_DELAY, RobotsChecker, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

COI_BASE = "https://www.constitutionofindia.net"
#COI_INDEX_URL = f"{COI_BASE}/historical-constitution/debates"
COI_INDEX_URL = f"{COI_BASE}/constitution-assembly-debates/"
COI_DAY_URL_PREFIX = f"{COI_BASE}/debates/"

def _default_volume_filter(url: str) -> bool:
    """Return True for volume-level pages on constitutionofindia.net."""
    return COI_BASE in url and "volume" in url.lower() and url.rstrip("/") != COI_INDEX_URL.rstrip("/")


def _default_day_filter(url: str) -> bool:
    """Return True for individual sitting pages (deeper than volume pages)."""
    if COI_BASE not in url:
        return False
    # A day URL has more path depth than a volume URL.
    # Volume URLs end with /volume-N/ or /volume-N; day URLs have an extra segment.
    # path = url.replace(COI_BASE, "").strip("/")
    path = url.replace(COI_DAY_URL_PREFIX, "").strip("/")
    parts = [p for p in path.split("/") if p]
    # Must be at least 3 levels deep (e.g. historical-constitution/debates/volume-1/1946-12-09)
    # and the last segment must not be a volume indicator
    #return len(parts) >= 3 and "volume" not in parts[-1].lower()
    # Day URLs have 2 path segments after the prefix: volume-N / YYYY-MM-DD
    return len(parts) == 2 and "volume" not in parts[-1].lower()


class CoidHtmlProvider(Provider):
    """constitutionofindia.net HTML provider for the CA corpus."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        rate_delay: float = DEFAULT_RATE_DELAY,
        robots_checker: RobotsChecker | None = None,
        index_url: str = COI_INDEX_URL,
        volume_url_filter: Callable[[str], bool] | None = None,
        day_url_filter: Callable[[str], bool] | None = None,
    ) -> None:
        self._client = client
        self._rate_delay = rate_delay
        self._robots = robots_checker or RobotsChecker()
        self._index_url = index_url
        self._volume_filter = volume_url_filter if volume_url_filter is not None else _default_volume_filter
        self._day_filter = day_url_filter if day_url_filter is not None else _default_day_filter

    async def discover(self) -> list[DocumentRef]:
        """
        Discover all CA sitting pages across 12 volumes.

        Crawls: index → volume pages → day pages.
        Returns one DocumentRef per sitting page.
        """
        volume_urls = await crawl_html_listing(
            self._client,
            self._index_url,
            link_filter=self._volume_filter,
        )
        if not volume_urls:
            logger.warning("coi_html: no volume URLs found on index %s", self._index_url)
            return []

        doc_refs: list[DocumentRef] = []
        seen: set[str] = set()

        for vol_idx, vol_url in enumerate(volume_urls, start=1):
            if not await self._robots.is_allowed(self._client, vol_url):
                logger.warning("coi_html: robots.txt disallows volume %s; skipping", vol_url)
                continue

            day_urls = await crawl_html_listing(
                self._client,
                vol_url,
                link_filter=self._day_filter,
            )
            if self._rate_delay > 0:
                await asyncio.sleep(self._rate_delay)

            for day_url in day_urls:
                if day_url in seen:
                    continue
                seen.add(day_url)
                doc_refs.append(
                    DocumentRef(
                        corpus="CA",
                        provider="coi_html",
                        format="html",
                        fetch_url=day_url,
                        canonical_doc_id=day_url,
                        citation_url=day_url,
                        metadata={"volume": vol_idx},
                    )
                )

        logger.info("coi_html: discovered %d CA sitting pages", len(doc_refs))
        return doc_refs

    async def fetch(self, doc_ref: DocumentRef) -> str | None:
        """Fetch the HTML content of a single CA sitting page."""
        if not await self._robots.is_allowed(self._client, doc_ref.fetch_url):
            logger.warning("coi_html: robots.txt disallows %s; skipping", doc_ref.fetch_url)
            return None

        resp = await fetch_with_retry(self._client, doc_ref.fetch_url)
        if resp is None:
            logger.warning("coi_html: could not fetch %s; skipping", doc_ref.fetch_url)
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        return resp.text
