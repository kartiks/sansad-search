"""
Shared discovery helpers for ingestion source providers.

Three helpers cover the three discovery patterns used across all corpora:
  - crawl_html_listing: fetch a listing/index page and extract matching links
  - paginate_dspace_browse: paginate DSpace browse-by-date to collect item URLs
  - enumerate_ia_search: paginate IA advancedsearch.php to collect identifiers
"""
from __future__ import annotations

import logging
import re
from typing import Callable
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ingest.sources._http import RateLimiter, fetch_with_retry

logger = logging.getLogger(__name__)

# Matches ISO dates (YYYY-MM-DD) at the start of a cell's text content
_DATE_CELL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _extract_row_date(tag) -> str | None:
    """Return the ISO date from the table row that contains *tag*, or None.

    DSpace browse rows follow:  <td><a href="/handle/...">Title</a></td>
                                <td>YYYY-MM-DD</td>
    Walks up to the parent <tr> and scans sibling <td> cells for an ISO date.
    Returns None (fail-safe: caller should include the item) if no date found.
    """
    row = tag.find_parent("tr")
    if row is None:
        return None
    for cell in row.find_all("td"):
        text = cell.get_text(strip=True)
        m = _DATE_CELL_RE.match(text)
        if m:
            return m.group(1)
    return None


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
    date_to: str | None = None,
    rpp: int = 20,
) -> list[str]:
    """
    Paginate a DSpace browse-by-date endpoint and return all item-page URLs.

    DSpace browse URLs follow the pattern:
      {browse_base_url}?type=dateissued&order=ASC&rpp={rpp}&offset={offset}

    Pagination continues until a page returns fewer items than rpp (last page),
    or until every item on a page exceeds date_to (early-break, ASC order).

    Args:
        client:          httpx.AsyncClient.
        browse_base_url: Base browse URL without query parameters, e.g.
                         "https://eparlib.sansad.in/browse".
        date_from:       Optional ISO date string (YYYY-MM-DD). Item URLs
                         for items with a metadata date before this are
                         excluded (best-effort, based on page-level date text).
        date_to:         Optional ISO date string (YYYY-MM-DD). Item URLs
                         for items with a metadata date after this are excluded.
                         When all items on a page exceed this bound, pagination
                         stops early (DSpace browse is ordered ASC by date).
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

        # found_on_page tracks ALL items for the pagination-stop criterion;
        # accepted_on_page is the date-filtered subset added to results.
        # all_items_past_date_to: True until an item that is NOT past date_to is found;
        # used for the early-break optimization (DSpace browse is ASC by date).
        found_on_page: list[str] = []
        accepted_on_page: list[str] = []
        all_items_past_date_to = True

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if "/handle/" in href:
                absolute = urljoin(base, href)
                if absolute not in item_urls and absolute not in found_on_page:
                    found_on_page.append(absolute)

                    # Compute row_date once for both filters
                    row_date: str | None = None
                    if date_from is not None or date_to is not None:
                        row_date = _extract_row_date(tag)

                    if date_from is not None and row_date is not None and row_date < date_from:
                        # Pre-scope: count for pagination but skip; not past date_to.
                        all_items_past_date_to = False
                        continue

                    if date_to is not None and row_date is not None and row_date > date_to:
                        # Post-scope: skip; item is past date_to (flag stays True).
                        continue
                    else:
                        # In-scope or no parseable date (fail-safe): include.
                        all_items_past_date_to = False

                    accepted_on_page.append(absolute)

        item_urls.extend(accepted_on_page)

        if len(found_on_page) < rpp:
            break
        # Early break: all items on this page exceeded date_to; no later page can match.
        if date_to is not None and found_on_page and all_items_past_date_to:
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
    date_to: str | None = None,
) -> list[dict]:
    """
    Enumerate results from archive.org advancedsearch.php.

    Deprecated for large collections: advancedsearch refuses to page past
    10,000 results. Use enumerate_ia_scrape() instead.

    Args:
        client:    httpx.AsyncClient.
        query:     Lucene query string, e.g. "identifier:(eparlib.nic.in*)".
        fields:    Metadata fields to return (fl[]). Defaults to ["identifier"].
        rows:      Results per page (default 100; IA maximum is 10,000).
        date_from: Optional ISO date string; filters on IA date metadata.
        date_to:   Optional ISO date string; upper bound for IA date metadata.
                   Combined with date_from: AND date:[{from} TO {to}].
                   Alone: AND date:[* TO {date_to}].

    Returns a list of result dicts, each containing the requested fields.
    """
    if fields is None:
        fields = ["identifier"]

    if date_from and date_to:
        query = f"{query} AND date:[{date_from} TO {date_to}]"
    elif date_from:
        query = f"{query} AND date:[{date_from} TO *]"
    elif date_to:
        query = f"{query} AND date:[* TO {date_to}]"

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


IA_SCRAPE_URL = "https://archive.org/services/search/v1/scrape"


def _ia_date_clause(query: str, date_from: str | None, date_to: str | None) -> str:
    if date_from or date_to:
        return f"{query} AND date:[{date_from or '*'} TO {date_to or '*'}]"
    return query


def _ia_item_matches(it: dict, prefix: str | None, date_from: str | None, date_to: str | None) -> bool:
    ident = str(it.get("identifier", ""))
    if prefix and not ident.startswith(prefix):
        return False
    d = str(it.get("date") or "")[:10]
    if d and ((date_from and d < date_from) or (date_to and d > date_to)):
        return False
    return True


def _ia_page_matches(
    items: list[dict], prefix: str | None, date_from: str | None, date_to: str | None
) -> bool:
    """
    True when the page plausibly answers our query (guards against IA's response
    cache, see enumerate_ia_scrape). A cache mix-up returns a page where nothing
    matches; a stray non-matching item among matching ones is tolerated and
    dropped individually.
    """
    if not items:
        return True
    ok = sum(_ia_item_matches(it, prefix, date_from, date_to) for it in items)
    return ok * 2 >= len(items)


async def enumerate_ia_scrape(
    client: httpx.AsyncClient,
    query: str,
    *,
    identifier_prefix: str | None = None,
    count: int = 5000,
    date_from: str | None = None,
    date_to: str | None = None,
    max_attempts: int = 4,
    limiter: RateLimiter | None = None,
) -> list[dict]:
    """
    Enumerate every archive.org item matching *query* via the Scraping API.

    Unlike advancedsearch.php (which refuses to page past 10,000 results and is
    therefore unusable for the ~390k-item eparlib collection), the Scraping API
    pages with an opaque cursor and has no depth limit.

    IA quirk (observed 2026-10): the first scrape page is cached by its ``fields``
    and ``count`` parameters while ignoring ``q``, so a request can come back with
    a *different query's* results. Every page is therefore checked against
    *identifier_prefix* and the date window; on a mismatch the first page is
    re-requested with a different ``count`` (a different cache key).

    Responses in advancedsearch shape ({"response": {"docs": [...]}}) are also
    accepted, so a single-page fixture works in tests.

    Raises RuntimeError when IA returns an error payload, a page cannot be
    fetched, or results keep failing validation — a failed listing is never
    mistaken for "no more items".
    """
    q = _ia_date_clause(query, date_from, date_to)
    base_count = max(100, min(count, 10000))   # IA bounds for the scrape API

    results: list[dict] = []
    cursor: str | None = None
    attempt = 0
    while True:
        page_count = base_count - 7 * attempt if not cursor else base_count
        params = {"q": q, "fields": "identifier,date", "count": str(max(100, page_count))}
        if cursor:
            params["cursor"] = cursor
        url = f"{IA_SCRAPE_URL}?{urlencode(params)}"
        resp = await fetch_with_retry(client, url, limiter=limiter)
        if resp is None:
            raise RuntimeError(f"IA scrape failed after {len(results)} items (query={q!r})")
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"IA scrape returned non-JSON after {len(results)} items: {exc}") from exc
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"IA scrape error after {len(results)} items: {data['error']}")

        items = data.get("items")
        if items is None:
            items = data.get("response", {}).get("docs", [])

        if not _ia_page_matches(items, identifier_prefix, date_from, date_to):
            if cursor is None and attempt + 1 < max_attempts:
                attempt += 1
                logger.warning(
                    "enumerate_ia_scrape: results do not match %r (IA cache); retrying", q
                )
                continue
            raise RuntimeError(f"IA scrape returned results that do not match {q!r}")

        results.extend(it for it in items if _ia_item_matches(it, identifier_prefix, date_from, date_to))
        cursor = data.get("cursor")
        if not cursor or not items:
            break

    logger.info("enumerate_ia_scrape: %d items for %r", len(results), q)
    return results
