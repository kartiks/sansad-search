"""
elibrary.sansad.in DSpace 7 provider for LS corpus.

Covers the "Text of Debates (English)" collection — official corrected English
transcripts of Lok Sabha debates from the 8th Lok Sabha (~1985) to the present.
Use with date_from="2019-01-01" (or after the IA provider cutoff) so that the
Internet Archive and this provider cover non-overlapping date ranges:
  InternetArchiveProvider  →  1947-08-15 to Aug 2018  (IA djvu.txt, best quality)
  ElibraryDSpace7Provider  →  2019-01-01 to present    (Tika-extracted PDF text)

Discovery:
  DSpace 7 search API paginated by date (ASC) →
  for each in-scope item: /core/items/{uuid}/bundles → TEXT bundle →
  /core/bundles/{text_uuid}/bitstreams → .pdf.txt bitstream UUID →
  fetch_url = /core/bitstreams/{bs_uuid}/content
  DocumentRef(format="elibrary_text", canonical_doc_id=handle_number,
              citation_url=elibrary_handle_url, metadata={date, lok_sabha_number,
              session_number})

Fetch:
  GET https://elibrary.sansad.in/server/api/core/bitstreams/{uuid}/content
  Returns str (Tika-extracted plain text, publicly accessible without auth).

RS note:
  No Rajya Sabha debates collection is available on elibrary.sansad.in as of
  June 2026.  RS coverage remains IA-only (1947–Aug 2018).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from ingest.sources._http import DEFAULT_RATE_DELAY, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

COLLECTION_UUID = "bba0ba48-e063-4938-94bb-f98e5a14b939"
ELIBRARY_API_BASE = "https://elibrary.sansad.in/server/api"
ELIBRARY_HANDLE_BASE = "https://elibrary.sansad.in/handle"

# DSpace 7 search page size; IA max is 100 but DSpace typically allows 100 too.
_PAGE_SIZE = 100

# Roman-numeral → int for session numbers (I–XX covers all plausible LS sessions)
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_meta(item: dict[str, Any], field: str) -> str | None:
    """Extract the first value of a DSpace 7 metadata field."""
    values = item.get("metadata", {}).get(field, [])
    if not values:
        return None
    return values[0].get("value")


def _extract_handle_number(handle: str) -> str | None:
    """
    Extract the numeric part N from a DSpace handle '123456789/N'.
    Returns None if the handle does not match the expected pattern.
    """
    m = re.match(r"123456789/(\d+)$", str(handle))
    return m.group(1) if m else None


def _parse_session_number(value: Any) -> int | None:
    """Convert a session-number value (int string or Roman numeral) to int."""
    if value is None:
        return None
    s = str(value).strip().upper()
    try:
        return int(s)
    except ValueError:
        return _ROMAN_TO_INT.get(s)


def _parse_lok_sabha_number(value: Any) -> int | None:
    """Parse the Lok Sabha number to int."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


# ── Provider ──────────────────────────────────────────────────────────────────

class ElibraryDSpace7Provider(Provider):
    """
    elibrary.sansad.in DSpace 7 provider for LS debates (English, post-2018).

    Discovers items in the "Text of Debates (English)" collection and resolves
    the pre-extracted plain-text (Tika) bitstream URL for each.  Subsequent
    fetch() calls download the text content.

    The provider contacts the DSpace 7 REST API (no authentication required for
    public content) and respects the rate_delay between API calls.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        date_from: str = "2019-01-01",
        date_to: str | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
        collection_uuid: str = COLLECTION_UUID,
    ) -> None:
        self._client = client
        self._date_from = date_from
        self._date_to = date_to
        self._rate_delay = rate_delay
        self._collection_uuid = collection_uuid

    # ── Public interface ───────────────────────────────────────────────────────

    async def discover(self) -> list[DocumentRef]:
        """
        Enumerate all in-scope items from the collection and resolve their
        TEXT bitstream URLs.

        Paginates the DSpace 7 search API (ASC by date), skips items before
        date_from, and stops once items exceed date_to (ASC ordering means
        once we pass the window, no later pages can match).

        Returns a list of DocumentRef objects ready for fetch().
        """
        doc_refs: list[DocumentRef] = []
        page = 0

        while True:
            search_url = (
                f"{ELIBRARY_API_BASE}/discover/search/objects"
                f"?scope={self._collection_uuid}"
                f"&sort=dc.date.issued%2CASC"
                f"&size={_PAGE_SIZE}"
                f"&page={page}"
            )

            resp = await fetch_with_retry(self._client, search_url)
            if resp is None:
                logger.warning(
                    "elibrary_dspace7: search fetch failed at page=%d; stopping", page
                )
                break

            try:
                data = resp.json()
            except Exception as exc:
                logger.error(
                    "elibrary_dspace7: JSON parse error at page=%d: %s; stopping",
                    page, exc,
                )
                break

            search_result = (
                data.get("_embedded", {}).get("searchResult", {})
            )
            objects = (
                search_result.get("_embedded", {}).get("objects", [])
            )

            if not objects:
                break  # Last page reached

            for obj in objects:
                item = obj.get("_embedded", {}).get("indexableObject", {})
                item_date = _get_meta(item, "dc.date.issued")

                # Pre-scope: skip
                if self._date_from and item_date and item_date < self._date_from:
                    continue

                # Post-scope: skip but keep paginating — the API sort order is
                # unreliable so later pages may still contain in-scope items.
                if self._date_to and item_date and item_date > self._date_to:
                    continue

                item_uuid = item.get("uuid")
                handle = item.get("handle", "")
                handle_n = _extract_handle_number(handle)

                if not item_uuid:
                    logger.warning("elibrary_dspace7: item with no UUID; skipping")
                    continue

                # Resolve the Tika plain-text bitstream URL (2 API calls per item)
                text_url = await self._get_text_bitstream_url(item_uuid)
                if text_url is None:
                    logger.warning(
                        "elibrary_dspace7: no TEXT bitstream for item %s (%s); skipping",
                        item_uuid, handle,
                    )
                    continue

                citation_url = f"{ELIBRARY_HANDLE_BASE}/{handle}"
                canonical_id = handle_n or item_uuid

                metadata = {
                    "date": item_date,
                    "lok_sabha_number": _parse_lok_sabha_number(
                        _get_meta(item, "dc.identifier.loksabhanumber")
                    ),
                    "session_number": _parse_session_number(
                        _get_meta(item, "dc.identifier.sessionnumber")
                    ),
                }

                doc_refs.append(
                    DocumentRef(
                        corpus="LS",
                        provider="elibrary_dspace7",
                        format="elibrary_text",
                        fetch_url=text_url,
                        canonical_doc_id=canonical_id,
                        citation_url=citation_url,
                        metadata=metadata,
                    )
                )

            # DSpace 7 pagination: stop when fewer items returned than page size
            if len(objects) < _PAGE_SIZE:
                break

            page += 1

        logger.info(
            "elibrary_dspace7: discovered %d LS documents (date_from=%s, date_to=%s)",
            len(doc_refs), self._date_from, self._date_to,
        )
        return doc_refs

    async def fetch(self, doc_ref: DocumentRef) -> str | None:
        """Download the pre-extracted plain-text content for one debate."""
        resp = await fetch_with_retry(self._client, doc_ref.fetch_url)
        if resp is None:
            logger.warning(
                "elibrary_dspace7: text fetch failed for %s; skipping",
                doc_ref.fetch_url,
            )
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        return resp.text

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_text_bitstream_url(self, item_uuid: str) -> str | None:
        """
        Resolve the Tika plain-text bitstream content URL for an item.

        Two API calls:
          1. GET /core/items/{uuid}/bundles   → find the 'TEXT' bundle UUID
          2. GET /core/bundles/{uuid}/bitstreams → find the .pdf.txt bitstream UUID

        Returns the content URL, or None if no TEXT bitstream is found.
        """
        # Step 1: bundles
        bundles_url = f"{ELIBRARY_API_BASE}/core/items/{item_uuid}/bundles"
        resp = await fetch_with_retry(self._client, bundles_url)
        if resp is None:
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        try:
            bundles_data = resp.json()
        except Exception:
            return None

        bundles = bundles_data.get("_embedded", {}).get("bundles", [])
        text_bundle = next(
            (b for b in bundles if b.get("name") == "TEXT"), None
        )
        if text_bundle is None:
            return None

        text_bundle_uuid = text_bundle.get("uuid")
        if not text_bundle_uuid:
            return None

        # Step 2: bitstreams in TEXT bundle
        bs_url = f"{ELIBRARY_API_BASE}/core/bundles/{text_bundle_uuid}/bitstreams"
        resp = await fetch_with_retry(self._client, bs_url)
        if resp is None:
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        try:
            bs_data = resp.json()
        except Exception:
            return None

        bitstreams = bs_data.get("_embedded", {}).get("bitstreams", [])

        # Prefer the .txt file (Tika extraction); fall back to first bitstream.
        txt_bs = next(
            (b for b in bitstreams if b.get("name", "").endswith(".txt")),
            bitstreams[0] if bitstreams else None,
        )
        if txt_bs is None:
            return None

        bs_uuid = txt_bs.get("uuid")
        if not bs_uuid:
            return None

        return f"{ELIBRARY_API_BASE}/core/bitstreams/{bs_uuid}/content"
