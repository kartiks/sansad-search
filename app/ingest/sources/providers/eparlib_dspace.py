"""
eparlib.sansad.in DSpace provider — LS fallback for items absent from IA.

Discovery:
  DSpace browse ?type=dateissued for collection handle /7 →
  one DocumentRef per item page (bitstream URL resolved during fetch).

Fetch:
  1. GET item page to extract the real bitstream URL.
  2. GET bitstream PDF.

Bitstream URLs are ALWAYS resolved from the item page — never constructed
from a filename pattern (ARCHITECTURE.md Key Design Patterns).

The DSpace handle number N (from /handle/123456789/{N}) is the cross-provider
join key shared with the Internet Archive provider (canonical_doc_id = N).
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.sources._discovery import paginate_dspace_browse
from ingest.sources._http import DEFAULT_RATE_DELAY, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

EPARLIB_BASE = "https://eparlib.sansad.in"
# Collection handle /7 scopes discovery to the LS collection only,
# excluding the CA-Legislative collection (handle /4).
EPARLIB_BROWSE_URL = f"{EPARLIB_BASE}/handle/123456789/7/browse"

# LS date scope from PRD
LS_DATE_FROM = "2014-01-01"

# Handle number N from DSpace item URL /handle/123456789/{N}
_HANDLE_RE = re.compile(r"/handle/\d+/(\d+)")


def _extract_handle_number(item_url: str) -> str | None:
    """Extract DSpace handle number N from a URL like /handle/123456789/N."""
    m = _HANDLE_RE.search(item_url)
    return m.group(1) if m else None


def _resolve_bitstream_url(html: str, base_url: str) -> str | None:
    """
    Resolve the real PDF bitstream URL from a DSpace item page.

    Reads the link from the page — never constructs filenames.
    """
    soup = BeautifulSoup(html, "lxml")
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    for a_tag in soup.find_all("a", href=True):
        href: str = a_tag["href"]
        if "/bitstream/" in href and href.lower().endswith(".pdf"):
            if href.startswith("http"):
                return href
            return base + href if href.startswith("/") else base + "/" + href

    return None


class EparlibDspaceProvider(Provider):
    """
    eparlib.sansad.in DSpace provider — LS fallback.

    Bitstream PDF URLs are resolved from the DSpace item page on demand
    during fetch(); they are never constructed from filename patterns.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        browse_url: str = EPARLIB_BROWSE_URL,
        date_from: str = LS_DATE_FROM,
        date_to: str | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
    ) -> None:
        self._client = client
        self._browse_url = browse_url
        self._date_from = date_from
        self._date_to = date_to
        self._rate_delay = rate_delay

    async def discover(self) -> list[DocumentRef]:
        """
        Paginate the DSpace browse-by-date endpoint and return one
        DocumentRef per item page.

        canonical_doc_id = handle number N (cross-provider join key shared
        with InternetArchiveProvider — if IA already processed N, the
        checkpoint store will skip this DocumentRef in the orchestrator).
        """
        item_urls = await paginate_dspace_browse(
            self._client,
            self._browse_url,
            date_from=self._date_from,
            date_to=self._date_to,
        )

        doc_refs: list[DocumentRef] = []
        for item_url in item_urls:
            handle_n = _extract_handle_number(item_url)
            if handle_n is None:
                logger.warning(
                    "eparlib_dspace: no handle number in %s; skipping", item_url
                )
                continue

            doc_refs.append(
                DocumentRef(
                    corpus="LS",
                    provider="eparlib_dspace",
                    format="pdf",
                    fetch_url=item_url,
                    canonical_doc_id=handle_n,
                    citation_url=None,  # absent from IA → no archive.org URL (Non-Neg #9 v3.0)
                    metadata={"item_url": item_url},
                )
            )

        logger.info("eparlib_dspace: discovered %d LS item pages", len(doc_refs))
        return doc_refs

    async def fetch(self, doc_ref: DocumentRef) -> bytes | None:
        """
        Fetch the PDF bitstream for a DSpace item.

        Step 1: Fetch the item page to resolve the real bitstream URL.
        Step 2: Fetch the PDF bytes from the resolved bitstream URL.

        Returns None if the item page is unreachable or contains no PDF link.
        """
        item_url = doc_ref.metadata.get("item_url") or doc_ref.fetch_url

        # Step 1: resolve bitstream URL from item page
        resp = await fetch_with_retry(self._client, item_url)
        if resp is None:
            logger.warning("eparlib_dspace: item page fetch failed for %s", item_url)
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        bitstream_url = _resolve_bitstream_url(resp.text, item_url)
        if bitstream_url is None:
            logger.warning(
                "eparlib_dspace: no PDF bitstream link on item page %s; skipping",
                item_url,
            )
            return None

        # Step 2: fetch the PDF
        pdf_resp = await fetch_with_retry(self._client, bitstream_url)
        if pdf_resp is None:
            logger.warning(
                "eparlib_dspace: PDF fetch failed for %s (item %s)", bitstream_url, item_url
            )
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        return pdf_resp.content
