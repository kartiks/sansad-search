"""
Shared discovery helpers for ingestion source providers.

Three helpers cover the three discovery patterns used across all corpora:
  - crawl_html_listing: fetch a listing/index page and extract matching links
  - paginate_dspace_browse: paginate DSpace browse-by-date to collect item URLs
  - enumerate_ia_search: paginate IA advancedsearch.php to collect identifiers
"""
from __future__ import annotations

import logging
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.sources._http import fetch_with_retry

logger = logging.getLogger(__name__)


async def crawl_html_listing(
    client: httpx.AsyncClient,
    listing_url: str,
    *,
    link_filter: Callable[[str], bool] | None = None,
    base_url: str | None = None,
) -> list[str]:
    """
    Fetch *listing_url* and return absolute URLs of all <a href> links.

    Args:
        client:       httpx.AsyncClient to use for the fetch.
        listing_url:  URL of the HTML listing/index page.
        link_filter:  Optional predicate applied to each resolved absolute URL;
                      only URLs for which it returns True are included.
        base_url:     Base URL for resolving relative hrefs. Defaults to
                      listing_url if not provided.

    Returns empty list if the page cannot be fetched.
    """
    resp = await fetch_with_retry(client, listing_url)
    if resp is None:
        logger.warning("crawl_html_listing: could not fetch %s", listing_url)
        return []

    base = base_url or listing_url
    soup = BeautifulSoup(resp.text, "lxml")
    urls: list[str] = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base, href)
        if link_filter is None or link_filter(absolute):
            urls.append(absolute)

    return urls


async def paginate_dspace_browse(
    client: httpx.AsyncClient,
    browse_base_url: str,
    *,
    date_from: str | None = None,
    rpp: int = 20,
) -> list[str]:
    """
    Paginate a DSpace browse-by-date endpoint and return all item-page URLs.

    DSpace browse URLs follow the pattern:
      {browse_base_url}?type=dateissued&order=ASC&rpp={rpp}&offset={offset}

    Pagination continues until a page returns fewer items than rpp (last page).

    Args:
        client:          httpx.AsyncClient.
        browse_base_url: Base browse URL without query parameters, e.g.
                         "https://eparlib.sansad.in/browse".
        date_from:       Optional ISO date string (YYYY-MM-DD). Item URLs
                         for items with a metadata date before this are
                         excluded (best-effort, based on page-level date text).
        rpp:             Results per page (default 20).

    Returns a list of absolute item-page URLs.
    """
    item_urls: list[str] = []
    offset = 0

    while True:
        page_url = (
            f"{browse_base_url}?type=dateissued&order=ASC"
            f"&rpp={rpp}&etal=-1&offset={offset}"
        )
        resp = await fetch_with_retry(client, page_url)
        if resp is None:
            logger.warning("paginate_dspace_browse: fetch failed at offset=%d", offset)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # DSpace item links appear as <a href="/handle/..."> within the browse table
        parsed = urlparse(browse_base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        found_on_page: list[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if "/handle/" in href:
                absolute = urljoin(base, href)
                if absolute not in item_urls and absolute not in found_on_page:
                    found_on_page.append(absolute)

        item_urls.extend(found_on_page)

        if len(found_on_page) < rpp:
            break
        offset += rpp

    return item_urls


async def enumerate_ia_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    fields: list[str] | None = None,
    rows: int = 100,
    date_from: str | None = None,
) -> list[dict]:
    """
    Enumerate all results from archive.org advancedsearch.php.

    Args:
        client:    httpx.AsyncClient.
        query:     Lucene query string, e.g. "identifier:(eparlib.nic.in*)".
        fields:    Metadata fields to return (fl[]). Defaults to ["identifier"].
        rows:      Results per page (default 100; IA maximum is 10,000).
        date_from: Optional ISO date string; filters on IA date metadata
                   (added to the query as AND date:[{date_from} TO *]).

    Returns a list of result dicts, each containing the requested fields.
    """
    if fields is None:
        fields = ["identifier"]

    if date_from:
        query = f"{query} AND date:[{date_from} TO *]"

    all_results: list[dict] = []
    page = 1

    while True:
        # Build query string
        fl_params = "&".join(f"fl[]={f}" for f in fields)
        search_url = (
            "https://archive.org/advancedsearch.php"
            f"?q={query}&output=json&{fl_params}&rows={rows}&page={page}"
        )

        resp = await fetch_with_retry(client, search_url)
        if resp is None:
            logger.warning("enumerate_ia_search: fetch failed on page=%d", page)
            break

        try:
            data = resp.json()
        except Exception as exc:
            logger.error("enumerate_ia_search: JSON parse error on page=%d: %s", page, exc)
            break

        docs: list[dict] = data.get("response", {}).get("docs", [])
        if not docs:
            break

        all_results.extend(docs)

        if len(docs) < rows:
            break
        page += 1

    return all_results
