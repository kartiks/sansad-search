"""
sansad.in/rs HTML provider — RS recent-sittings primary source.

Two-level discovery:
  1. Crawl the RS debates listing page (/rs/debates/officials) to collect
     per-sitting page URLs.
  2. Return one DocumentRef per sitting page (format=html, corpus=RS).

Date scope: only sittings dated >= 2014-01-01 are in scope. The sitting date is
read from the listing-page URL (best-effort); URLs without a parseable date are
included (fail-safe) and the downstream parser/date-scope guard handles them.

canonical_doc_id: the per-sitting page URL (sansad.in/rs has no DSpace handle;
the page URL is its own canonical identity per DATA-MODELS §4.3 — same pattern as
the CA coi_html provider).

citation_url: the same per-sitting page URL (appears as source_url in records).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import Callable

import httpx

from ingest.sources._discovery import crawl_html_listing
from ingest.sources._http import DEFAULT_RATE_DELAY, RobotsChecker, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

SANSAD_BASE = "https://sansad.in"
SANSAD_RS_LISTING_URL = f"{SANSAD_BASE}/rs/debates/officials"

# RS date scope from PRD
RS_DATE_FROM = "2014-01-01"

# Date embedded in a sitting URL, e.g. /rs/debates/officials/2023/03/15 or
# .../2023-03-15. Matches YYYY[sep]MM[sep]DD with / _ or - separators.
_URL_DATE_RE = re.compile(r"[/_-](\d{4})[/_-](\d{2})[/_-](\d{2})")


def _date_from_url(url: str) -> date | None:
    """Extract a sitting date from a URL path. Returns None if absent/invalid."""
    m = _URL_DATE_RE.search(url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _default_sitting_filter(url: str) -> bool:
    """Return True for individual RS sitting pages under the debates listing.

    A sitting page lives deeper than the listing root and stays on sansad.in.
    The listing root itself is excluded.
    """
    if SANSAD_BASE not in url:
        return False
    if url.rstrip("/") == SANSAD_RS_LISTING_URL.rstrip("/"):
        return False
    return "/rs/debates/" in url


class SansadRsHtmlProvider(Provider):
    """sansad.in/rs HTML provider for the RS corpus (recent in-scope sittings)."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        rate_delay: float = DEFAULT_RATE_DELAY,
        robots_checker: RobotsChecker | None = None,
        listing_url: str = SANSAD_RS_LISTING_URL,
        date_from: str = RS_DATE_FROM,
        sitting_url_filter: Callable[[str], bool] | None = None,
    ) -> None:
        self._client = client
        self._rate_delay = rate_delay
        self._robots = robots_checker or RobotsChecker()
        self._listing_url = listing_url
        self._date_from = date.fromisoformat(date_from)
        self._sitting_filter = (
            sitting_url_filter
            if sitting_url_filter is not None
            else _default_sitting_filter
        )

    async def discover(self) -> list[DocumentRef]:
        """
        Crawl the RS debates listing and return one DocumentRef per sitting page.

        URLs dated before the date scope (2014-01-01) are excluded. URLs with no
        parseable date are retained (fail-safe).
        """
        sitting_urls = await crawl_html_listing(
            self._client,
            self._listing_url,
            link_filter=self._sitting_filter,
        )
        if not sitting_urls:
            logger.warning(
                "sansad_rs_html: no sitting URLs found on listing %s",
                self._listing_url,
            )
            return []

        doc_refs: list[DocumentRef] = []
        seen: set[str] = set()

        for url in sitting_urls:
            if url in seen:
                continue
            seen.add(url)

            doc_date = _date_from_url(url)
            if doc_date is not None and doc_date < self._date_from:
                continue  # out of scope (pre-2014)

            doc_refs.append(
                DocumentRef(
                    corpus="RS",
                    provider="sansad_rs_html",
                    format="html",
                    fetch_url=url,
                    canonical_doc_id=url,
                    citation_url=url,
                    metadata={"sitting_date": doc_date.isoformat() if doc_date else None},
                )
            )

        logger.info("sansad_rs_html: discovered %d RS sitting pages", len(doc_refs))
        return doc_refs

    async def fetch(self, doc_ref: DocumentRef) -> str | None:
        """Fetch the HTML content of a single RS sitting page."""
        if not await self._robots.is_allowed(self._client, doc_ref.fetch_url):
            logger.warning(
                "sansad_rs_html: robots.txt disallows %s; skipping", doc_ref.fetch_url
            )
            return None

        resp = await fetch_with_retry(self._client, doc_ref.fetch_url)
        if resp is None:
            logger.warning(
                "sansad_rs_html: could not fetch %s; skipping", doc_ref.fetch_url
            )
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        return resp.text
