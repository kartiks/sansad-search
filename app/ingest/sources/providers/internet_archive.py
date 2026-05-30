"""
Internet Archive provider for LS corpus (Phase 8) and RS corpus (Phase 9).

Discovery:
  advancedsearch.php enumerate eparlib.nic.in.{N} identifiers →
  metadata JSON fetch per identifier (https://archive.org/metadata/{id}) →
  DocumentRef(format=ia_text, canonical_doc_id=N, citation_url=eparlib_document_url)

Fetch:
  GET https://archive.org/download/{identifier}/{identifier}_djvu.txt
  Returns str (IA _djvu.txt text content).

Non-Negotiable #9: citation_url is NEVER an archive.org URL. For LS,
citation_url = eparlib_document_url from metadata. For RS (Phase 9 extension),
citation_url = rsdebate.nic.in URL derived from handle N.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from ingest.sources._discovery import enumerate_ia_search
from ingest.sources._http import DEFAULT_RATE_DELAY, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

# Matches eparlib.nic.in.{N} — N is the cross-provider DSpace handle number
_IDENTIFIER_RE = re.compile(r"eparlib\.nic\.in\.(\d+)$", re.IGNORECASE)

_IA_METADATA_BASE = "https://archive.org/metadata"
_IA_DJVU_PATTERN = "https://archive.org/download/{id}/{id}_djvu.txt"

# Fields to request from IA advancedsearch (used to build the initial identifier list)
_IA_SEARCH_FIELDS = ["identifier"]


def _extract_handle_number(identifier: str) -> str | None:
    """Extract the DSpace handle number N from eparlib.nic.in.{N}."""
    m = _IDENTIFIER_RE.match(str(identifier))
    return m.group(1) if m else None


def _get_meta(raw: dict[str, Any], key: str) -> str | None:
    """Extract a metadata value that may be a string or single-element list."""
    val = raw.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return str(val)


class InternetArchiveProvider(Provider):
    """
    Internet Archive provider — enumerates eparlib.nic.in.{N} items.

    Two-step discovery: advancedsearch to enumerate identifiers, then a
    metadata JSON fetch per identifier to populate eparlib_* fields and
    determine citation_url.

    corpus="LS" (Phase 8): citation_url = eparlib_document_url.
    corpus="RS" (Phase 9, subclassed): citation_url = rsdebate.nic.in URL.
    """

    IA_QUERY = "identifier:(eparlib.nic.in*)"

    def __init__(
        self,
        client: httpx.AsyncClient,
        corpus: str = "LS",
        *,
        date_from: str = "2014-01-01",
        rate_delay: float = DEFAULT_RATE_DELAY,
        ia_query: str | None = None,
    ) -> None:
        if corpus not in ("LS", "RS"):
            raise ValueError(f"corpus must be 'LS' or 'RS'; got {corpus!r}")
        self._client = client
        self._corpus = corpus
        self._date_from = date_from
        self._rate_delay = rate_delay
        self._query = ia_query or self.IA_QUERY

    async def discover(self) -> list[DocumentRef]:
        """
        Enumerate all eparlib.nic.in.{N} identifiers and build DocumentRefs.

        For each identifier: fetches the IA metadata JSON to get eparlib_* fields,
        extracts the DSpace handle number N as canonical_doc_id, sets citation_url
        to eparlib_document_url (never archive.org — Non-Negotiable #9).
        """
        ia_results = await enumerate_ia_search(
            self._client,
            self._query,
            fields=_IA_SEARCH_FIELDS,
            date_from=self._date_from,
        )

        doc_refs: list[DocumentRef] = []
        for item in ia_results:
            identifier = item.get("identifier")
            if not identifier:
                continue

            handle_n = _extract_handle_number(str(identifier))
            if handle_n is None:
                logger.warning(
                    "IA identifier %r does not match eparlib.nic.in.{N}; skipping",
                    identifier,
                )
                continue

            meta = await self._fetch_ia_metadata(str(identifier))
            if meta is None:
                continue

            citation_url = self._build_citation_url(meta, handle_n)
            djvu_url = _IA_DJVU_PATTERN.format(id=identifier)

            doc_refs.append(
                DocumentRef(
                    corpus=self._corpus,
                    provider="internet_archive",
                    format="ia_text",
                    fetch_url=djvu_url,
                    canonical_doc_id=handle_n,
                    citation_url=citation_url,
                    metadata={
                        "identifier": str(identifier),
                        "eparlib_document_url": _get_meta(meta, "eparlib_document_url"),
                        "eparlib_date": _get_meta(meta, "eparlib_date"),
                        "eparlib_lok_sabha_number": _get_meta(meta, "eparlib_lok_sabha_number"),
                        "eparlib_session_number": _get_meta(meta, "eparlib_session_number"),
                        "eparlib_title": _get_meta(meta, "eparlib_title"),
                        "title": _get_meta(meta, "title"),
                    },
                )
            )

        logger.info(
            "internet_archive: discovered %d %s documents", len(doc_refs), self._corpus
        )
        return doc_refs

    def _build_citation_url(self, meta: dict[str, Any], handle_n: str) -> str | None:
        """
        Return the canonical citation URL. Never returns an archive.org URL.

        LS: eparlib_document_url from metadata.
        RS: override in subclass or Phase 9 extension.
        """
        if self._corpus == "LS":
            return _get_meta(meta, "eparlib_document_url")
        # RS extension implemented in Phase 9
        return None

    async def _fetch_ia_metadata(self, identifier: str) -> dict[str, Any] | None:
        """Fetch IA metadata JSON for one identifier. Returns the metadata sub-dict."""
        meta_url = f"{_IA_METADATA_BASE}/{identifier}"
        resp = await fetch_with_retry(self._client, meta_url)
        if resp is None:
            logger.warning("IA metadata fetch failed for %s; skipping", identifier)
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        try:
            data = resp.json()
        except Exception as exc:
            logger.error("IA metadata JSON parse error for %s: %s", identifier, exc)
            return None

        return data.get("metadata", {})

    async def fetch(self, doc_ref: DocumentRef) -> str | None:
        """Fetch the _djvu.txt content for a single IA document."""
        resp = await fetch_with_retry(self._client, doc_ref.fetch_url)
        if resp is None:
            logger.warning(
                "IA _djvu.txt fetch failed for %s; skipping", doc_ref.fetch_url
            )
            return None

        if self._rate_delay > 0:
            await asyncio.sleep(self._rate_delay)

        return resp.text
