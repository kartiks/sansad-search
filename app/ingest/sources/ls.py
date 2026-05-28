"""
Lok Sabha source: discovers and fetches LS parliamentary records from 2014-01-01.

URL discovery: fetches the LS business index page and extracts document links.
HTML format is preferred over PDF when both are available for the same sitting.
Only records dated 2014-01-01 or later are in scope.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import AsyncGenerator, Optional, Union

import httpx
from bs4 import BeautifulSoup

from ingest.sources._http import (
    DEFAULT_RATE_DELAY,
    RobotsChecker,
    fetch_with_retry,
)

logger = logging.getLogger(__name__)

LS_SCOPE_FROM: date = date(2014, 1, 1)
LS_INDEX_URL: str = "https://sansad.in/ls/business/debatesandquestions"

# URL path fragments used to infer proceeding type from link href
_LS_PROCEEDING_HINTS: list[tuple[str, str]] = [
    ("unstarredquestion", "unstarred_question"),
    ("unstarred_question", "unstarred_question"),
    ("starredquestion", "starred_question"),
    ("starred_question", "starred_question"),
    ("adjournmentmotion", "adjournment_motion"),
    ("adjournment_motion", "adjournment_motion"),
    ("callingattention", "calling_attention"),
    ("calling_attention", "calling_attention"),
    ("shortduration", "short_duration_discussion"),
    ("short_duration", "short_duration_discussion"),
    ("shortnoticequestion", "short_notice_question"),
    ("short_notice", "short_notice_question"),
    ("privatememberbill", "private_member_bill"),
    ("private_member", "private_member_bill"),
    ("zerohour", "zero_hour"),
    ("zero_hour", "zero_hour"),
    ("debate", "debate"),
]


def _infer_proceeding_type(url: str) -> Optional[str]:
    """Guess proceeding type from URL path. Returns None if unrecognised."""
    lower = url.lower()
    for fragment, pt in _LS_PROCEEDING_HINTS:
        if fragment in lower:
            return pt
    return None


def _date_from_url(url: str) -> Optional[date]:
    """Extract date from URL path (e.g. /2023/03/15/ or /20230315/)."""
    m = re.search(r"[/_-](\d{4})[/_-](\d{2})[/_-](\d{2})", url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _sitting_key(url: str) -> str:
    """Produce a date-based key for HTML/PDF deduplication (same sitting)."""
    # Strip extension so .html and .pdf of the same document share a key
    base = re.sub(r"\.(html?|pdf)$", "", url, flags=re.IGNORECASE)
    return base


class LSSource:
    """
    Discovers and fetches LS parliamentary records from 2014-01-01.

    URL discovery reads the LS index page and extracts document links.
    For each unique sitting, the HTML version is preferred over PDF.
    """

    def __init__(
        self,
        rate_delay: float = DEFAULT_RATE_DELAY,
        date_from: date = LS_SCOPE_FROM,
        robots_checker: Optional[RobotsChecker] = None,
        index_url: str = LS_INDEX_URL,
    ) -> None:
        self.rate_delay = rate_delay
        self.date_from = date_from
        self.robots_checker = robots_checker or RobotsChecker()
        self.index_url = index_url

    async def discover_document_urls(
        self, client: httpx.AsyncClient
    ) -> list[tuple[str, Optional[str]]]:
        """
        Fetch the LS index page and return (url, proceeding_type_hint) pairs.

        - Excludes documents dated before self.date_from
        - For the same sitting, HTML is preferred; PDF alternative is excluded
        """
        resp = await fetch_with_retry(client, self.index_url)
        if resp is None:
            logger.error("Could not fetch LS index page %s", self.index_url)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        seen_keys: dict[str, str] = {}  # sitting_key → preferred_url

        for a_tag in soup.find_all("a", href=True):
            href: str = a_tag["href"].strip()
            if not href:
                continue
            if not href.startswith("http"):
                href = (
                    "https://sansad.in" + href
                    if href.startswith("/")
                    else "https://sansad.in/" + href
                )

            # Date scope filter
            doc_date = _date_from_url(href)
            if doc_date is not None and doc_date < self.date_from:
                continue

            key = _sitting_key(href)
            existing = seen_keys.get(key)
            is_html = not href.lower().endswith(".pdf")

            if existing is None:
                seen_keys[key] = href
            elif is_html and existing.lower().endswith(".pdf"):
                # Prefer HTML over PDF for the same sitting
                seen_keys[key] = href

        result: list[tuple[str, Optional[str]]] = [
            (url, _infer_proceeding_type(url)) for url in seen_keys.values()
        ]
        return result

    async def fetch_documents(
        self,
        client: httpx.AsyncClient,
    ) -> AsyncGenerator[tuple[str, Union[str, bytes], dict], None]:
        """
        Async generator yielding (url, content, metadata) for each LS document.

        content is str for HTML documents, bytes for PDFs.
        metadata: {"source": "LS", "proceeding_type_hint": str | None}
        """
        urls = await self.discover_document_urls(client)
        for url, proceeding_hint in urls:
            if not await self.robots_checker.is_allowed(client, url):
                logger.warning("robots.txt disallows %s; skipping", url)
                continue

            resp = await fetch_with_retry(client, url)
            if resp is None:
                continue

            content: Union[str, bytes] = (
                resp.content if url.lower().endswith(".pdf") else resp.text
            )
            yield url, content, {
                "source": "LS",
                "proceeding_type_hint": proceeding_hint,
            }

            if self.rate_delay > 0:
                await asyncio.sleep(self.rate_delay)
