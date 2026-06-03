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


def _extract_stage1_fields(raw_record: dict) -> tuple[Optional[str], dict]:
    """Split parser output into (extracted_text, metadata_json) for Stage 1 write."""
    extracted_text = raw_record.get("raw_text")
    metadata = {k: v for k, v in raw_record.items() if k not in ("raw_text", "raw_html")}
    return extracted_text, metadata


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

    Phase 12: split into run_stage1() and run_stage2() for the two-stage pipeline.
    - Stage 1: provider chain → fetch → parse → write to raw_documents (PK dedup)
    - Stage 2: read from raw_documents → segment → canonicalize → index
    run() calls both in sequence for --stage all.

    PRD v2.0 change (Phase 10): shared sequence_within_sitting is assigned at
    orchestrator level across all records (speech + Q+A) within each sitting,
    in the order documents are processed from the provider chain.

    BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 1 — LS):
    LS documents from InternetArchiveProvider are individual per-session
    proceeding-type files (one file per proceeding type per sitting). Speeches
    and Q+A exchanges appear in separate documents. The shared sitting-level
    sequence reflects the order documents are discovered and processed by the
    provider chain. For IA, discovery order follows the advancedsearch.php
    result order (sorted by date). Within a sitting, the proceeding-type
    ordering is not guaranteed to match the official parliamentary order
    (Question Hour before debates). This is a known limitation of the
    document-at-a-time processing model. Finding recorded: 2026-06-02.
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
        _df = {"date_from": date_from} if date_from is not None else {}
        self._providers: list[Provider] = providers or [
            InternetArchiveProvider(client, corpus="LS", rate_delay=rate_delay, **_df),
            EparlibDspaceProvider(client, rate_delay=rate_delay, **_df),
        ]
        # Per-sitting sequence counter shared across all providers and record types
        self._sitting_seq: dict[str, int] = {}

    def _next_seq(self, sitting_key: str) -> int:
        n = self._sitting_seq.get(sitting_key, 1)
        self._sitting_seq[sitting_key] = n + 1
        return n

    def _sitting_key(self, record: dict) -> str:
        return f"LS_{record.get('date', '')}_{record.get('sitting_number')}"

    async def run_stage1(self) -> dict[str, int]:
        """
        Stage 1: discover LS documents across the provider chain, fetch, parse,
        write to raw_documents.

        Dedup guard: indexer.check_raw_document_exists() (PK lookup).
        No SQLite checkpoint writes in Stage 1.
        Returns stats: fetched, skipped, errors.
        """
        stats: dict[str, int] = {"fetched": 0, "skipped": 0, "errors": 0}

        for provider in self._providers:
            doc_refs = await provider.discover()
            logger.info(
                "ls_stage1: provider=%s discovered %d documents",
                provider.__class__.__name__, len(doc_refs),
            )

            for doc_ref in doc_refs:
                if self._indexer.check_raw_document_exists(doc_ref.canonical_doc_id):
                    logger.debug("ls_stage1: already fetched %s; skipping", doc_ref.canonical_doc_id)
                    stats["skipped"] += 1
                    continue

                content = await provider.fetch(doc_ref)
                if content is None:
                    logger.warning("ls_stage1: fetch failed for %s; skipping", doc_ref.canonical_doc_id)
                    stats["errors"] += 1
                    continue

                raw_record = self._parse(content, doc_ref)
                if raw_record is None:
                    stats["errors"] += 1
                    continue

                extracted_text, metadata = _extract_stage1_fields(raw_record)

                self._indexer.write_raw_document(
                    canonical_doc_id=doc_ref.canonical_doc_id,
                    corpus="LS",
                    date=raw_record.get("date"),
                    provider=doc_ref.provider,
                    format=doc_ref.format,
                    extracted_text=extracted_text,
                    metadata_json=metadata,
                    fetch_url=doc_ref.fetch_url,
                    citation_url=doc_ref.citation_url,
                )
                stats["fetched"] += 1

        logger.info(
            "ls_stage1: done — fetched=%d skipped=%d errors=%d",
            stats["fetched"], stats["skipped"], stats["errors"],
        )
        return stats

    async def run_stage2(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Stage 2: read raw_documents for LS, segment, canonicalize, index.

        Resumability: SQLite processed_documents checkpoint guards re-runs.
        Returns stats: indexed, skipped, errors.
        """
        stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

        rows = list(self._indexer.read_raw_documents_for_scope("LS", date_from, date_to))
        logger.info("ls_stage2: %d raw_documents rows to process", len(rows))

        for row in rows:
            canonical_doc_id = row["canonical_doc_id"]
            if self._checkpoint.is_document_processed(canonical_doc_id):
                logger.debug("ls_stage2: already processed %s; skipping", canonical_doc_id)
                stats["skipped"] += 1
                continue

            raw_record = dict(row["metadata_json"])
            if row["extracted_text"] is not None:
                raw_record["raw_text"] = row["extracted_text"]

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
                record["sequence_within_sitting"] = self._next_seq(
                    self._sitting_key(record)
                )

                if self._indexer.index_record(record, self._checkpoint):
                    stats["indexed"] += 1

            self._checkpoint.mark_document_processed(
                canonical_doc_id,
                corpus="LS",
                provider=row["provider"],
                fetch_url=row["fetch_url"],
            )

        logger.info(
            "ls_stage2: done — indexed=%d skipped=%d errors=%d",
            stats["indexed"], stats["skipped"], stats["errors"],
        )
        return stats

    async def run(self) -> dict[str, int]:
        """Run full LS ingestion (--stage all): Stage 1 then Stage 2."""
        s1 = await self.run_stage1()
        s2 = await self.run_stage2()
        return {
            "indexed": s2["indexed"],
            "skipped": s2["skipped"],
            "errors": s1["errors"] + s2["errors"],
        }

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
