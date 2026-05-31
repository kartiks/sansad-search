"""
Lok Sabha ingestion.

Provides two components:
  - LSSource  — legacy Phase 1-2 fetcher (HTML/PDF from sansad.in index page).
                Kept for backward compatibility; superseded by LSOrchestrator.
  - LSOrchestrator — Phase 8+ orchestrator using the multi-provider chain
                     [InternetArchiveProvider, EparlibDspaceProvider].
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from typing import AsyncGenerator, Optional, Union

import httpx
from bs4 import BeautifulSoup

from ingest.canonical.names import canonicalize_name
from ingest.canonical.sessions import canonicalize_session
from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest.parsers.ia_text_parser import parse_ia_text
from ingest.parsers.pdf_parser import parse_pdf
from ingest.segmenters.qa import segment_qa
from ingest.segmenters.speech import segment_speeches
from ingest.sources._http import (
    DEFAULT_RATE_DELAY,
    RobotsChecker,
    fetch_with_retry,
)
from ingest.sources._provider import Provider
from ingest.sources.providers.eparlib_dspace import EparlibDspaceProvider
from ingest.sources.providers.internet_archive import InternetArchiveProvider

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


# ── Phase 8+ Orchestrator ─────────────────────────────────────────────────────


class LSOrchestrator:
    """
    LS corpus orchestrator — provider chain: [InternetArchiveProvider, EparlibDspaceProvider].

    Iterates providers in order. For each provider:
      - discover() → list[DocumentRef]
      - For each DocumentRef: checkpoint check → fetch → parse → segment → index

    Document-level dedup via canonical_doc_id (= DSpace handle number N) shared
    across both providers ensures each document is fetched and parsed once even
    when it appears in both IA and DSpace.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        checkpoint: CheckpointStore,
        indexer: Indexer,
        names_dict: dict[str, str] | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
        providers: Optional[list[Provider]] = None,
        date_from: Optional[str] = None,
    ) -> None:
        self._client = client
        self._checkpoint = checkpoint
        self._indexer = indexer
        self._names_dict = names_dict or {}
        self._rate_delay = rate_delay
        self._date_from = date_from
        # date_from (ISO YYYY-MM-DD) overrides the providers' built-in scope.
        # When None, each default provider keeps its own 2014-01-01 PRD-scope
        # default. Injected providers are used as-is.
        _df = {"date_from": date_from} if date_from is not None else {}
        self._providers: list[Provider] = providers or [
            InternetArchiveProvider(client, corpus="LS", rate_delay=rate_delay, **_df),
            EparlibDspaceProvider(client, rate_delay=rate_delay, **_df),
        ]

    async def run(self) -> dict[str, int]:
        """
        Run LS ingestion across the provider chain.

        Returns stats: indexed, skipped, errors.
        """
        stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

        for provider in self._providers:
            doc_refs = await provider.discover()
            logger.info(
                "ls_orchestrator: provider=%s discovered %d documents",
                provider.__class__.__name__,
                len(doc_refs),
            )

            for doc_ref in doc_refs:
                if self._checkpoint.is_document_processed(doc_ref.canonical_doc_id):
                    logger.debug(
                        "ls_orchestrator: already processed doc_id=%s; skipping",
                        doc_ref.canonical_doc_id,
                    )
                    stats["skipped"] += 1
                    continue

                content = await provider.fetch(doc_ref)
                if content is None:
                    logger.warning(
                        "ls_orchestrator: fetch failed for %s; skipping",
                        doc_ref.canonical_doc_id,
                    )
                    stats["errors"] += 1
                    continue

                raw_record = self._parse(content, doc_ref)
                if raw_record is None:
                    stats["errors"] += 1
                    continue

                records = self._segment(raw_record)
                for record in records:
                    if record.get("record_type") == "speech":
                        canon_name, unresolved = canonicalize_name(
                            record.get("speaker_name"), self._names_dict
                        )
                        record["speaker_name"] = canon_name
                        record["speaker_name_unresolved"] = unresolved
                    record["session_name"] = canonicalize_session(
                        record.get("session_name"), source="LS"
                    )

                    if self._indexer.index_record(record, self._checkpoint):
                        stats["indexed"] += 1

                self._checkpoint.mark_document_processed(
                    doc_ref.canonical_doc_id,
                    corpus="LS",
                    provider=doc_ref.provider,
                    fetch_url=doc_ref.fetch_url,
                )

        logger.info(
            "ls_orchestrator: done — indexed=%d skipped=%d errors=%d",
            stats["indexed"],
            stats["skipped"],
            stats["errors"],
        )
        return stats

    def _parse(self, content: str | bytes, doc_ref) -> dict | None:
        """Dispatch to the correct parser based on doc_ref.format."""
        try:
            if doc_ref.format == "ia_text":
                return parse_ia_text(content, doc_ref.metadata, source="LS")
            if doc_ref.format == "pdf":
                return parse_pdf(
                    content,
                    source="LS",
                    source_url=doc_ref.citation_url,
                )
            logger.warning(
                "ls_orchestrator: unrecognised format %r for %s; skipping",
                doc_ref.format,
                doc_ref.canonical_doc_id,
            )
        except Exception as exc:
            logger.error(
                "ls_orchestrator: parse error for %s: %s; skipping",
                doc_ref.canonical_doc_id,
                exc,
            )
        return None

    def _segment(self, raw_record: dict) -> list[dict]:
        """Segment a raw record into speech + Q+A units."""
        pt = raw_record.get("proceeding_type")
        if pt in ("starred_question", "unstarred_question"):
            records = segment_qa(raw_record, source="LS", proceeding_type=pt)
            for r in records:
                r["record_type"] = "qa"
        else:
            records = segment_speeches(raw_record, source="LS")
            for r in records:
                r["record_type"] = "speech"
        return records
