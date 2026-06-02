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
#   YYYY-MM-DD  (e.g. "1946-12-09")  — ISO format also observed in some URL patterns
_CA_URL_SLUG_DMY_RE = re.compile(r"^(\d{1,2})-([a-z]{3})-(\d{4})$", re.IGNORECASE)
_CA_URL_SLUG_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_CA_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
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


class CAOrchestrator:
    """
    CA corpus orchestrator — provider chain: [CoidHtmlProvider].

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
    ) -> None:
        self._client = client
        self._checkpoint = checkpoint
        self._indexer = indexer
        self._names_dict = names_dict or {}
        self._rate_delay = rate_delay
        self._provider: Provider = provider or CoidHtmlProvider(
            client, rate_delay=rate_delay
        )
        # Per-sitting sequence counter: sitting_key → next sequence number
        self._sitting_seq: dict[str, int] = {}

    def _next_seq(self, sitting_key: str) -> int:
        n = self._sitting_seq.get(sitting_key, 1)
        self._sitting_seq[sitting_key] = n + 1
        return n

    async def run(self) -> dict[str, int]:
        """
        Run CA ingestion. Returns stats: indexed, skipped, errors.

        Document-level dedup via checkpoint store prevents reprocessing on re-run.
        """
        stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

        doc_refs = await self._provider.discover()
        logger.info("ca_orchestrator: discovered %d CA documents", len(doc_refs))

        for doc_ref in doc_refs:
            if self._checkpoint.is_document_processed(doc_ref.canonical_doc_id):
                logger.debug(
                    "ca_orchestrator: already processed %s; skipping",
                    doc_ref.canonical_doc_id,
                )
                stats["skipped"] += 1
                continue

            content = await self._provider.fetch(doc_ref)
            if content is None:
                logger.warning(
                    "ca_orchestrator: fetch failed for %s; skipping",
                    doc_ref.canonical_doc_id,
                )
                stats["errors"] += 1
                continue

            try:
                raw_record = parse_html(
                    content,
                    source="CA",
                    source_url=doc_ref.citation_url,
                )
            except Exception as exc:
                logger.error(
                    "ca_orchestrator: parse error for %s: %s; skipping",
                    doc_ref.canonical_doc_id,
                    exc,
                )
                stats["errors"] += 1
                continue

            # CA date: URL slug is always authoritative (PRD v2.0 F01 CA rules).
            # Override whatever html_parser returned — even when it found a date.
            ca_date = _extract_ca_date_from_url(doc_ref.fetch_url)
            if ca_date:
                raw_record["date"] = ca_date
            else:
                logger.warning(
                    "ca_orchestrator: could not extract date from URL %s for %s; skipping",
                    doc_ref.fetch_url,
                    doc_ref.canonical_doc_id,
                )
                stats["errors"] += 1
                continue

            if not raw_record.get("date"):
                logger.warning(
                    "ca_orchestrator: no date for %s; skipping",
                    doc_ref.canonical_doc_id,
                )
                stats["errors"] += 1
                continue

            speeches = segment_speeches(raw_record, source="CA")

            # Sitting key for shared sequence: CA records group by source + date
            # (sitting_number is null for CA; date alone identifies the sitting)
            sitting_key = f"CA_{raw_record['date']}"

            for speech in speeches:
                speech["volume"] = doc_ref.metadata.get("volume")
                canon_name, unresolved = canonicalize_name(
                    speech.get("speaker_name"), self._names_dict
                )
                speech["speaker_name"] = canon_name
                speech["speaker_name_unresolved"] = unresolved
                speech["session_name"] = None
                speech["session_number"] = None
                speech["record_type"] = "speech"

                # Assign shared sequence at orchestrator level (not in segmenter)
                speech["sequence_within_sitting"] = self._next_seq(sitting_key)

                if self._indexer.index_record(speech, self._checkpoint):
                    stats["indexed"] += 1

            # Mark document fully processed (even when no speeches — document is done)
            self._checkpoint.mark_document_processed(
                doc_ref.canonical_doc_id,
                corpus="CA",
                provider=doc_ref.provider,
                fetch_url=doc_ref.fetch_url,
            )

        logger.info(
            "ca_orchestrator: done — indexed=%d skipped=%d errors=%d",
            stats["indexed"],
            stats["skipped"],
            stats["errors"],
        )
        return stats
