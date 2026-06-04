"""
Constituent Assembly ingestion.

Provides two components:
  - CASource  — legacy Phase 1-2 fetcher (PDF volumes from sansad.in).
                Kept for backward compatibility; superseded by CAOrchestrator.
  - CAOrchestrator — Phase 8+ orchestrator using the CoidHtmlProvider chain.
                     Implements discover → fetch → parse → segment → index.

PRD v2.0 changes (Phase 10):
  - CA date always derived from URL slug (authoritative per F01 CA parsing rules).
    HTML body date is discarded even when present.
  - Shared sequence_within_sitting assigned at orchestrator level across all
    speech and Q+A records within each sitting in document order.
    CA has no Q+A exchanges; sequence is assigned to speeches only.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date as _date
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx

from ingest.canonical.names import canonicalize_name, load_names_dict
from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest.parsers.html_parser import parse_html
from ingest.segmenters.speech import segment_speeches
from ingest.sources._http import (
    DEFAULT_RATE_DELAY,
    RobotsChecker,
    fetch_with_retry,
)
from ingest.sources._provider import DocumentRef, Provider
from ingest.sources.providers.coi_html import CoidHtmlProvider

logger = logging.getLogger(__name__)

# Base URL for CA PDF volumes on sansad.in (legacy)
CA_VOLUME_BASE = "https://sansad.in/getFile/constitutiondebates"

CA_VOLUME_URLS: list[str] = [
    f"{CA_VOLUME_BASE}/Volume_{i:02d}.pdf" for i in range(1, 13)
]

# CA URL slug formats:
#   DD-MMM-YYYY (e.g. "09-dec-1946") — PRD canonical format
#   DD-MMMM-YYYY (e.g. "29-july-1947") — full month name, also observed on the live site
#   YYYY-MM-DD  (e.g. "1946-12-09")  — ISO format also observed in some URL patterns
_CA_URL_SLUG_DMY_RE = re.compile(r"^(\d{1,2})-([a-z]{3,9})-(\d{4})$", re.IGNORECASE)
_CA_URL_SLUG_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_CA_MONTH_ABBR = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _extract_ca_date_from_url(fetch_url: str) -> str | None:
    """
    Extract the sitting date from a constitutionofindia.net URL slug.

    Handles both:
    - DD-MMM-YYYY format (e.g. "09-dec-1946") — PRD canonical
    - YYYY-MM-DD format  (e.g. "1946-12-09")  — ISO, also seen in URL patterns

    Returns ISO date string YYYY-MM-DD, or None if the slug cannot be parsed.

    Per PRD v2.0 F01 CA field-level parsing rules: the URL slug is the
    authoritative date source for CA records. Any date extracted from the HTML
    body is discarded; this function's result always takes precedence.
    """
    slug = fetch_url.rstrip("/").rsplit("/", 1)[-1]

    # Try DD-MMM-YYYY first (PRD canonical format)
    m = _CA_URL_SLUG_DMY_RE.match(slug)
    if m:
        month = _CA_MONTH_ABBR.get(m.group(2).lower())
        if month:
            try:
                return _date(int(m.group(3)), month, int(m.group(1))).isoformat()
            except ValueError:
                pass

    # Try ISO YYYY-MM-DD format
    m = _CA_URL_SLUG_ISO_RE.match(slug)
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass

    return None


class CASource:
    """
    Fetches all 12 Constituent Assembly debate PDF volumes from sansad.in.
    Legacy — superseded by CAOrchestrator.
    """

    def __init__(
        self,
        rate_delay: float = DEFAULT_RATE_DELAY,
        robots_checker: Optional[RobotsChecker] = None,
        volume_urls: Optional[list[str]] = None,
    ) -> None:
        self.rate_delay = rate_delay
        self.robots_checker = robots_checker or RobotsChecker()
        self._volume_urls = volume_urls if volume_urls is not None else CA_VOLUME_URLS

    def enumerate_urls(self) -> list[str]:
        """Return the ordered list of CA volume PDF URLs (12 items)."""
        return list(self._volume_urls)

    async def fetch_documents(
        self,
        client: httpx.AsyncClient,
    ) -> AsyncGenerator[tuple[str, bytes, dict], None]:
        for i, url in enumerate(self.enumerate_urls(), start=1):
            if not await self.robots_checker.is_allowed(client, url):
                logger.warning("robots.txt disallows %s; skipping", url)
                continue

            resp = await fetch_with_retry(client, url)
            if resp is None:
                logger.warning("Skipping CA volume %d (%s)", i, url)
                continue

            yield url, resp.content, {"source": "CA", "volume": i}

            if self.rate_delay > 0:
                await asyncio.sleep(self.rate_delay)


# ── Phase 8+ Orchestrator ─────────────────────────────────────────────────────


def _extract_stage1_fields(raw_record: dict) -> tuple[Optional[str], dict]:
    """
    Split a parser-output raw_record into (extracted_text, metadata_json).

    ``extracted_text`` is the raw_text field (consumed by segmenters).
    ``metadata_json`` contains all other fields needed to reconstruct the
    raw_record in Stage 2, minus raw_html (large, not used by segmenters).
    """
    extracted_text = raw_record.get("raw_text")
    metadata = {
        k: v for k, v in raw_record.items()
        if k not in ("raw_text", "raw_html")
    }
    return extracted_text, metadata


class CAOrchestrator:
    """
    CA corpus orchestrator — provider chain: [CoidHtmlProvider].

    Phase 12: split into run_stage1() and run_stage2() for the two-stage pipeline.
    - Stage 1: discover → fetch → parse → write to raw_documents (PK dedup)
    - Stage 2: read from raw_documents → segment → canonicalize → index
    run() calls both in sequence for --stage all.

    PRD v2.0 changes (Phase 10):
    - CA date always overridden from URL slug (F01 CA field-level parsing rules).
    - Shared sequence_within_sitting assigned at orchestrator level.
      CA has no Q+A exchanges; sequence is 1-based for speeches in DOM order.

    BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 1 — CA shared sequence):
    constitutionofindia.net serves one HTML page per sitting day. All debate
    speeches for a sitting appear in that page in DOM order. CA has no Question
    Hour (no Q+A exchanges), so the shared sequence space for CA contains only
    speech records. The sitting-level sequence is reliably assignable from
    document order without cross-type interleaving. Finding recorded: 2026-06-02.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        checkpoint: CheckpointStore,
        indexer: Indexer,
        names_dict: dict[str, str] | None = None,
        rate_delay: float = DEFAULT_RATE_DELAY,
        provider: Optional[Provider] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> None:
        self._client = client
        self._checkpoint = checkpoint
        self._indexer = indexer
        self._names_dict = names_dict or {}
        self._rate_delay = rate_delay
        self._date_from = date_from
        self._date_to = date_to
        self._provider: Provider = provider or CoidHtmlProvider(
            client, rate_delay=rate_delay, date_from=date_from, date_to=date_to
        )
        # Per-sitting sequence counter: sitting_key → next sequence number
        self._sitting_seq: dict[str, int] = {}

    def _next_seq(self, sitting_key: str) -> int:
        n = self._sitting_seq.get(sitting_key, 1)
        self._sitting_seq[sitting_key] = n + 1
        return n

    async def run_stage1(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Stage 1: discover CA documents, fetch, parse, write to raw_documents.

        Dedup guard: indexer.check_raw_document_exists() (PK lookup in PostgreSQL).
        No SQLite checkpoint writes in Stage 1.
        date_from/date_to: post-parse date gate — documents outside the window
        are counted as skipped and not written to raw_documents.
        Returns stats: fetched, skipped, errors.
        """
        stats: dict[str, int] = {"fetched": 0, "skipped": 0, "errors": 0}

        doc_refs = await self._provider.discover()
        logger.info("ca_stage1: discovered %d CA documents", len(doc_refs))

        for doc_ref in doc_refs:
            if self._indexer.check_raw_document_exists(doc_ref.canonical_doc_id):
                logger.debug("ca_stage1: already fetched %s; skipping", doc_ref.canonical_doc_id)
                stats["skipped"] += 1
                continue

            content = await self._provider.fetch(doc_ref)
            if content is None:
                logger.warning("ca_stage1: fetch failed for %s; skipping", doc_ref.canonical_doc_id)
                stats["errors"] += 1
                continue

            try:
                raw_record = parse_html(content, source="CA", source_url=doc_ref.citation_url)
            except Exception as exc:
                logger.error("ca_stage1: parse error for %s: %s; skipping", doc_ref.canonical_doc_id, exc)
                stats["errors"] += 1
                continue

            # CA date: URL slug is always authoritative (PRD v2.0 F01 CA rules)
            ca_date = _extract_ca_date_from_url(doc_ref.fetch_url)
            if ca_date:
                raw_record["date"] = ca_date
            else:
                logger.warning(
                    "ca_stage1: could not extract date from URL %s for %s; "
                    "writing row with null date",
                    doc_ref.fetch_url,
                    doc_ref.canonical_doc_id,
                )

            doc_date = raw_record.get("date")
            if date_from and doc_date and doc_date < date_from:
                stats["skipped"] += 1
                continue
            if date_to and doc_date and doc_date > date_to:
                stats["skipped"] += 1
                continue

            extracted_text, metadata = _extract_stage1_fields(raw_record)
            metadata["volume"] = doc_ref.metadata.get("volume")

            self._indexer.write_raw_document(
                canonical_doc_id=doc_ref.canonical_doc_id,
                corpus="CA",
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
            "ca_stage1: done — fetched=%d skipped=%d errors=%d",
            stats["fetched"], stats["skipped"], stats["errors"],
        )
        return stats

    async def run_stage2(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Stage 2: read raw_documents for CA, segment, canonicalize, index.

        Resumability: SQLite processed_documents checkpoint guards re-runs.
        Returns stats: indexed, skipped, errors.
        """
        stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

        rows = list(self._indexer.read_raw_documents_for_scope("CA", date_from, date_to))
        logger.info("ca_stage2: %d raw_documents rows to process", len(rows))

        for row in rows:
            canonical_doc_id = row["canonical_doc_id"]
            if self._checkpoint.is_document_processed(canonical_doc_id):
                logger.debug("ca_stage2: already processed %s; skipping", canonical_doc_id)
                stats["skipped"] += 1
                continue

            raw_record = dict(row["metadata_json"])
            if row["extracted_text"] is not None:
                raw_record["raw_text"] = row["extracted_text"]

            speeches = segment_speeches(raw_record, source="CA")

            if not speeches:
                logger.warning(
                    "ca_stage2: no speeches extracted from %s — "
                    "HTML structure may not match expected speech row pattern; "
                    "document checkpointed as processed with 0 records",
                    canonical_doc_id,
                )

            sitting_key = f"CA_{raw_record.get('date', '')}"

            for speech in speeches:
                speech["volume"] = row["metadata_json"].get("volume")
                canon_name, unresolved = canonicalize_name(
                    speech.get("speaker_name"), self._names_dict
                )
                speech["speaker_name"] = canon_name
                speech["speaker_name_unresolved"] = unresolved
                speech["session_name"] = None
                speech["session_number"] = None
                speech["record_type"] = "speech"
                speech["sequence_within_sitting"] = self._next_seq(sitting_key)

                if self._indexer.index_record(speech, self._checkpoint):
                    stats["indexed"] += 1

            self._checkpoint.mark_document_processed(
                canonical_doc_id,
                corpus="CA",
                provider=row["provider"],
                fetch_url=row["fetch_url"],
            )

        logger.info(
            "ca_stage2: done — indexed=%d skipped=%d errors=%d",
            stats["indexed"], stats["skipped"], stats["errors"],
        )
        return stats

    async def run(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Run full CA ingestion (--stage all): Stage 1 then Stage 2.

        Returns combined stats. "skipped" reflects Stage 2 document-level skips
        (already-processed documents), consistent with the pre-Phase-12 semantics.
        """
        s1 = await self.run_stage1(date_from=date_from, date_to=date_to)
        s2 = await self.run_stage2(date_from=date_from, date_to=date_to)
        return {
            "indexed": s2["indexed"],
            "skipped": s2["skipped"],
            "errors": s1["errors"] + s2["errors"],
        }
