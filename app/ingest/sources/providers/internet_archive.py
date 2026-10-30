"""
Internet Archive provider for the LS corpus (eparlib.nic.in.* mirror, Lok Sabha
Secretariat) and the RS corpus (rsdebate.nic.in.* mirror, Rajya Sabha Secretariat).

Discovery:
  IA Scraping API (cursor-paged) enumerates {eparlib|rsdebate}.nic.in.{N} identifiers →
  metadata JSON fetch per identifier (https://archive.org/metadata/{id}) →
  locate DjVuTXT entry in top-level `files` array (format == "DjVuTXT") →
  build fetch_url as https://{server}{dir}/{name} →
  DocumentRef(format=ia_text, canonical_doc_id=N, citation_url=archive.org item URL)

Fetch:
  GET https://{server}{dir}/{name}  (DjVuTXT file served from IA content server)
  Returns str (IA _djvu.txt text content).

Non-Negotiable #9 (REVERSED in PRD v3.0): citation_url IS the Internet Archive
item URL — `https://archive.org/details/{identifier}` — for both LS and RS.
The prior rule (eparlib_document_url for LS, rsdebate.nic.in for RS) is no
longer used. citation_url is null only when no IA identifier is derivable.

lok_sabha_number (PRD v3.0): extracted from `eparlib_lok_sabha_number` in the
IA metadata JSON for LS items only (RS and CA are always null). Surfaced on the
DocumentRef metadata as the integer `lok_sabha_number`.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

import httpx

from ingest.sources._discovery import enumerate_ia_scrape
from ingest.sources._http import DEFAULT_RATE_DELAY, fetch_with_retry
from ingest.sources._provider import DocumentRef, Provider

logger = logging.getLogger(__name__)

# Matches eparlib.nic.in.{N} — N is the cross-provider DSpace handle number
_IDENTIFIER_RE = re.compile(r"eparlib\.nic\.in\.(\d+)$", re.IGNORECASE)
# Matches rsdebate.nic.in.{N} — the Rajya Sabha debates mirror (rsdebate.nic.in handle N)
_RS_IDENTIFIER_RE = re.compile(r"rsdebate\.nic\.in\.(\d+)$", re.IGNORECASE)

# Each house has its own IA mirror. eparlib.nic.in.* is published by the Lok Sabha
# Secretariat (every item, checked 2026-10) and also holds ~9k committee reports,
# which are not proceedings. rsdebate.nic.in.* is the Rajya Sabha Secretariat's
# mirror (1952 – Dec 2009 as of 2026-10).
_LS_QUERY = (
    'identifier:eparlib.nic.in* '
    'AND NOT eparlib_appears_in_collections:"Parliamentary Committee Reports"'
)
_RS_QUERY = "identifier:rsdebate.nic.in*"
_CORPUS_CONFIG: dict[str, dict[str, Any]] = {
    "LS": {"query": _LS_QUERY, "prefix": "eparlib.nic.in.", "id_re": _IDENTIFIER_RE},
    "RS": {"query": _RS_QUERY, "prefix": "rsdebate.nic.in.", "id_re": _RS_IDENTIFIER_RE},
}

# rsdebate_* metadata → the eparlib_* keys ia_text_parser reads
_RS_FIELD_MAP = {
    "rsdebate_document_url": "eparlib_document_url",
    "rsdebate_debate_date": "eparlib_date",
    "rsdebate_session_number": "eparlib_session_number",
    "rsdebate_debate_title": "eparlib_title",
    "rsdebate_question_type": "eparlib_question_type",
    "rsdebate_question_number": "eparlib_question_number",
    "rsdebate_questioner_name": "eparlib_members",
    "rsdebate_ministry": "eparlib_relation_ministry",
    "rsdebate_ministers_name": "eparlib_minister_name",
    "rsdebate_page_number_from_to": "eparlib_page_range",
}

_IA_METADATA_BASE = "https://archive.org/metadata"

# PRD v3.0: the Internet Archive item page is now the canonical citation
# (source_url) for both LS and RS records (Non-Negotiable #9 reversal).
IA_DETAILS_BASE = "https://archive.org/details"
IA_ITEM_PATTERN = f"{IA_DETAILS_BASE}/{{identifier}}"

# rsdebate.nic.in handle pattern — retained for the RS DSpace fallback provider
# and for tests; no longer used to build the IA citation_url (PRD v3.0 reversal).
RSDEBATE_BASE = "https://rsdebate.nic.in"
RSDEBATE_ITEM_PATTERN = f"{RSDEBATE_BASE}/handle/123456789/{{handle}}"

# Fields to request from IA advancedsearch (used to build the initial identifier list)
_IA_SEARCH_FIELDS = ["identifier"]


def _extract_handle_number(identifier: str, pattern: re.Pattern = _IDENTIFIER_RE) -> str | None:
    """Extract the DSpace handle number N from eparlib.nic.in.{N} (or rsdebate.nic.in.{N})."""
    m = pattern.match(str(identifier))
    return m.group(1) if m else None


def _rs_metadata_as_eparlib(meta: dict[str, Any]) -> dict[str, Any]:
    """Return *meta* with rsdebate_* fields copied onto the eparlib_* names the parser reads."""
    out = dict(meta)
    for src, dst in _RS_FIELD_MAP.items():
        if meta.get(src) not in (None, "", []) and out.get(dst) in (None, "", []):
            out[dst] = meta[src]
    return out


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

    corpus="LS" or corpus="RS": citation_url = archive.org item URL
    (https://archive.org/details/{identifier}) — Non-Negotiable #9 v3.0 reversal.
    Null only when no IA identifier is derivable.
    """

    IA_QUERY = _LS_QUERY  # LS default; RS uses _RS_QUERY

    def __init__(
        self,
        client: httpx.AsyncClient,
        corpus: str = "LS",
        *,
        date_from: str = "2014-01-01",
        date_to: str | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
        ia_query: str | None = None,
        is_known: Callable[[str], bool] | None = None,
    ) -> None:
        if corpus not in ("LS", "RS"):
            raise ValueError(f"corpus must be 'LS' or 'RS'; got {corpus!r}")
        cfg = _CORPUS_CONFIG[corpus]
        self._client = client
        self._corpus = corpus
        self._date_from = date_from
        self._date_to = date_to
        self._rate_delay = rate_delay
        self._query = ia_query or cfg["query"]
        self._prefix = cfg["prefix"]
        self._id_re = cfg["id_re"]
        # Skips the per-item metadata request for documents already stored.
        self._is_known = is_known

    async def discover(self) -> list[DocumentRef]:
        """
        Enumerate all eparlib.nic.in.{N} identifiers and build DocumentRefs.

        For each identifier: fetches the IA metadata JSON to get eparlib_* fields,
        extracts the DSpace handle number N as canonical_doc_id, sets citation_url
        to the archive.org item URL (Non-Negotiable #9 v3.0 — archive.org is the
        canonical citation for both LS and RS records fetched via IA).
        """
        ia_results = await enumerate_ia_scrape(
            self._client,
            self._query,
            identifier_prefix=self._prefix,
            date_from=self._date_from,
            date_to=self._date_to,
        )

        doc_refs: list[DocumentRef] = []
        known = 0
        for item in ia_results:
            identifier = item.get("identifier")
            if not identifier:
                continue

            handle_n = _extract_handle_number(str(identifier), self._id_re)
            if handle_n is None:
                logger.warning(
                    "IA identifier %r does not match %s{N}; skipping", identifier, self._prefix
                )
                continue

            if self._is_known is not None and self._is_known(handle_n):
                known += 1
                continue

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
            if self._corpus == "RS":
                meta = _rs_metadata_as_eparlib(meta)
            if "committee" in str(_get_meta(meta, "eparlib_appears_in_collections") or "").lower():
                logger.debug("IA item %r is a committee report; skipping", identifier)
                continue
            citation_url = self._build_citation_url(str(identifier))
            canonical_id = handle_n

            # PRD v3.0: lok_sabha_number is LS-only, derived from the IA metadata
            # field eparlib_lok_sabha_number. RS and CA are always null.
            lok_sabha_number = (
                self._extract_lok_sabha_number(meta)
                if self._corpus == "LS"
                else None
            )

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
                        "lok_sabha_number": lok_sabha_number,
                        "eparlib_document_url": _get_meta(meta, "eparlib_document_url"),
                        "eparlib_date": _get_meta(meta, "eparlib_date"),
                        "eparlib_lok_sabha_number": _get_meta(meta, "eparlib_lok_sabha_number"),
                        "eparlib_session_number": _get_meta(meta, "eparlib_session_number"),
                        "eparlib_title": _get_meta(meta, "eparlib_title"),
                        "eparlib_question_type": _get_meta(meta, "eparlib_question_type"),
                        "eparlib_question_number": _get_meta(meta, "eparlib_question_number"),
                        "eparlib_members": meta.get("eparlib_members"),  # may be a list
                        "eparlib_relation_ministry": _get_meta(meta, "eparlib_relation_ministry"),
                        "eparlib_minister_name": _get_meta(meta, "eparlib_minister_name"),
                        "eparlib_page_range": _get_meta(meta, "eparlib_page_range"),
                        "title": _get_meta(meta, "title"),
                    },
                )
            )

        logger.info(
            "internet_archive: discovered %d new %s documents (%d already stored)",
            len(doc_refs), self._corpus, known,
        )
        return doc_refs

    def _build_citation_url(self, identifier: str | None) -> str | None:
        """
        Return the canonical citation URL — the Internet Archive item page.

        PRD v3.0 (Non-Negotiable #9 reversal): the archive.org item URL
        (`https://archive.org/details/{identifier}`) is the citation for both
        LS and RS. eparlib_document_url (LS) and the rsdebate.nic.in handle URL
        (RS) are no longer used. Returns None only when no IA identifier exists.
        """
        if not identifier:
            return None
        return IA_ITEM_PATTERN.format(identifier=identifier)

    @staticmethod
    def _extract_lok_sabha_number(meta: dict[str, Any]) -> int | None:
        """
        Parse eparlib_lok_sabha_number to an int. Returns None when absent or
        unparseable. LS-only gating is applied at the corpus level (RS/CA pass
        no eparlib_lok_sabha_number).
        """
        raw = _get_meta(meta, "eparlib_lok_sabha_number")
        if raw is None:
            return None
        try:
            return int(str(raw).strip())
        except (ValueError, TypeError):
            logger.warning(
                "eparlib_lok_sabha_number %r is not an integer; ignoring", raw
            )
            return None

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
