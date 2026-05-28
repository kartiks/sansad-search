"""
Rajya Sabha source: discovers and fetches RS parliamentary records from 2014-01-01.

Mirror of ls.py but for rajyasabha.gov.in.
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

RS_SCOPE_FROM: date = date(2014, 1, 1)
RS_INDEX_URL: str = "https://rajyasabha.gov.in/rsnew/business/parlamentary_business.asp"

# URL path fragments → proceeding type (RS may use different URL patterns)
_RS_PROCEEDING_HINTS: list[tuple[str, str]] = [
    ("unstarredqst", "unstarred_question"),
    ("unstarred_qst", "unstarred_question"),
    ("unstarred", "unstarred_question"),
    ("starredqst", "starred_question"),
    ("starred_qst", "starred_question"),
    ("starred", "starred_question"),
    ("adjournment", "adjournment_motion"),
    ("calling_attention", "calling_attention"),
    ("callingattention", "calling_attention"),
    ("shortduration", "short_duration_discussion"),
    ("short_duration", "short_duration_discussion"),
    ("short_notice", "short_notice_question"),
    ("shortnotice", "short_notice_question"),
    ("privatememberbill", "private_member_bill"),
    ("private_member", "private_member_bill"),
    ("zerohour", "zero_hour"),
    ("zero_hour", "zero_hour"),
    ("debate", "debate"),
]


def _infer_proceeding_type(url: str) -> Optional[str]:
    """Guess RS proceeding type from URL path. Returns None if unrecognised."""
    lower = url.lower()
    for fragment, pt in _RS_PROCEEDING_HINTS:
        if fragment in lower:
            return pt
    return None


def _date_from_url(url: str) -> Optional[date]:
    """Extract date from URL path."""
    m = re.search(r"[/_-](\d{4})[/_-](\d{2})[/_-](\d{2})", url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _sitting_key(url: str) -> str:
    """Produce a date-based key for HTML/PDF deduplication."""
    return re.sub(r"\.(html?|pdf)$", "", url, flags=re.IGNORECASE)


class RSSource:
    """
    Discovers and fetches RS parliamentary records from 2014-01-01.

    Fetches the RS index page and extracts document links.
    HTML is preferred over PDF for the same sitting.
    """

    def __init__(
        self,
        rate_delay: float = DEFAULT_RATE_DELAY,
        date_from: date = RS_SCOPE_FROM,
        robots_checker: Optional[RobotsChecker] = None,
        index_url: str = RS_INDEX_URL,
    ) -> None:
        self.rate_delay = rate_delay
        self.date_from = date_from
        self.robots_checker = robots_checker or RobotsChecker()
        self.index_url = index_url

    async def discover_document_urls(
        self, client: httpx.AsyncClient
    ) -> list[tuple[str, Optional[str]]]:
        """
        Fetch the RS index page and return (url, proceeding_type_hint) pairs.
        """
        resp = await fetch_with_retry(client, self.index_url)
        if resp is None:
            logger.error("Could not fetch RS index page %s", self.index_url)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        seen_keys: dict[str, str] = {}

        for a_tag in soup.find_all("a", href=True):
            href: str = a_tag["href"].strip()
            if not href:
                continue
            if not href.startswith("http"):
                href = (
                    "https://rajyasabha.gov.in" + href
                    if href.startswith("/")
                    else "https://rajyasabha.gov.in/" + href
                )

            doc_date = _date_from_url(href)
            if doc_date is not None and doc_date < self.date_from:
                continue

            key = _sitting_key(href)
            existing = seen_keys.get(key)
            is_html = not href.lower().endswith(".pdf")

            if existing is None:
                seen_keys[key] = href
            elif is_html and existing.lower().endswith(".pdf"):
                seen_keys[key] = href

        return [
            (url, _infer_proceeding_type(url)) for url in seen_keys.values()
        ]

    async def fetch_documents(
        self,
        client: httpx.AsyncClient,
    ) -> AsyncGenerator[tuple[str, Union[str, bytes], dict], None]:
        """
        Async generator yielding (url, content, metadata) for each RS document.
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
                "source": "RS",
                "proceeding_type_hint": proceeding_hint,
            }

            if self.rate_delay > 0:
                await asyncio.sleep(self.rate_delay)
