"""
Internet Archive provider for LS corpus (Phase 8) and RS corpus (Phase 9).

Discovery:
  advancedsearch.php enumerate eparlib.nic.in.{N} identifiers →
  metadata JSON fetch per identifier (https://archive.org/metadata/{id}) →
  locate DjVuTXT entry in top-level `files` array (format == "DjVuTXT") →
  build fetch_url as https://{server}{dir}/{name} →
  DocumentRef(format=ia_text, canonical_doc_id=N, citation_url=eparlib_document_url)

Fetch:
  GET https://{server}{dir}/{name}  (DjVuTXT file served from IA content server)
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

# rsdebate.nic.in is the canonical RS citation host (DSpace). The handle number N
# extracted from the IA identifier is the same DSpace handle used on rsdebate.
# Non-Negotiable #9: this URL is cited instead of the archive.org mirror.
RSDEBATE_BASE = "https://rsdebate.nic.in"
RSDEBATE_ITEM_PATTERN = f"{RSDEBATE_BASE}/handle/123456789/{{handle}}"

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
        date_to: str | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
        ia_query: str | None = None,
    ) -> None:
        if corpus not in ("LS", "RS"):
            raise ValueError(f"corpus must be 'LS' or 'RS'; got {corpus!r}")
        self._client = client
        self._corpus = corpus
        self._date_from = date_from
        self._date_to = date_to
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
            date_to=self._date_to,
        )

        doc_refs: list[DocumentRef] = []
        for item in ia_results:
            identifier = item.get("identifier")
            if not identifier:
                continue

            handle_n = _extract_handle_number(str(identifier))
            if handle_n is None:
                if self._corpus == "LS":
                    logger.warning(
                        "IA identifier %r does not match eparlib.nic.in.{N}; skipping",
                        identifier,
                    )
                    continue
                # RS: retain the item but no DSpace handle is derivable, so no
                # canonical rsdebate.nic.in citation can be built (PRD v1.3 edge
                # case). citation_url=None; the archive.org URL is never used.
                logger.warning(
                    "RS IA identifier %r has no derivable DSpace handle; "
                    "citation_url set to null (PRD v1.3 edge case)",
                    identifier,
                )

            full_data = await self._fetch_ia_metadata(str(identifier))
            if full_data is None:
                continue

            files = full_data.get("files", [])
            djvu_entry = next(
                (f for f in files if f.get("format") == "DjVuTXT"), None
            )
            if djvu_entry is None:
                logger.warning(
                    "IA item %r has no DjVuTXT file; skipping", identifier
                )
                continue

            server = full_data.get("server", "")
            dir_ = full_data.get("dir", "")
            djvu_url = f"https://{server}{dir_}/{djvu_entry['name']}"

            meta = full_data.get("metadata", {})
            citation_url = self._build_citation_url(meta, handle_n)
            # When no DSpace handle is derivable (RS edge case), fall back to the
            # IA identifier as the checkpoint/dedup key so the item is still
            # tracked for resumability.
            canonical_id = handle_n if handle_n is not None else str(identifier)

            doc_refs.append(
                DocumentRef(
                    corpus=self._corpus,
                    provider="internet_archive",
                    format="ia_text",
                    fetch_url=djvu_url,
                    canonical_doc_id=canonical_id,
                    citation_url=citation_url,
                    metadata={
                        "identifier": str(identifier),
                        "eparlib_document_url": _get_meta(meta, "eparlib_document_url"),
                        "eparlib_date": _get_meta(meta, "eparlib_date"),
                        "eparlib_lok_sabha_number": _get_meta(meta, "eparlib_lok_sabha_number"),
                        "eparlib_session_number": _get_meta(meta, "eparlib_session_number"),
                        "eparlib_title": _get_meta(meta, "eparlib_title"),
                        "eparlib_question_type": _get_meta(meta, "eparlib_question_type"),
                        "eparlib_question_number": _get_meta(meta, "eparlib_question_number"),
                        "eparlib_members": meta.get("eparlib_members"),  # may be a list
                        "eparlib_relation_ministry": _get_meta(meta, "eparlib_relation_ministry"),
                        "title": _get_meta(meta, "title"),
                    },
                )
            )

        logger.info(
            "internet_archive: discovered %d %s documents", len(doc_refs), self._corpus
        )
        return doc_refs

    def _build_citation_url(
        self, meta: dict[str, Any], handle_n: str | None
    ) -> str | None:
        """
        Return the canonical citation URL. Never returns an archive.org URL.

        LS: eparlib_document_url from metadata.
        RS: rsdebate.nic.in item URL derived from the DSpace handle number N
            (PRD v1.3). When N is not derivable, returns None — the archive.org
            mirror URL is never substituted (Non-Negotiable #9).
        """
        if self._corpus == "LS":
            return _get_meta(meta, "eparlib_document_url")
        # RS (PRD v1.3): canonical citation is rsdebate.nic.in, derived from handle N.
        if handle_n is None:
            return None
        return RSDEBATE_ITEM_PATTERN.format(handle=handle_n)

    async def _fetch_ia_metadata(self, identifier: str) -> dict[str, Any] | None:
        """Fetch IA metadata JSON for one identifier. Returns the full top-level JSON dict."""
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

        return data

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
