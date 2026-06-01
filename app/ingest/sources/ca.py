"""
Constituent Assembly ingestion.

Provides two components:
  - CASource  — legacy Phase 1-2 fetcher (PDF volumes from sansad.in).
                Kept for backward compatibility; superseded by CAOrchestrator.
  - CAOrchestrator — Phase 8+ orchestrator using the CoidHtmlProvider chain.
                     Implements discover → fetch → parse → segment → index.
"""
from __future__ import annotations

import asyncio
import logging
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

# Base URL for CA PDF volumes on sansad.in
CA_VOLUME_BASE = "https://sansad.in/getFile/constitutiondebates"

# All 12 Constituent Assembly Debates volumes (fixed, no discovery needed)
CA_VOLUME_URLS: list[str] = [
    f"{CA_VOLUME_BASE}/Volume_{i:02d}.pdf" for i in range(1, 13)
]


class CASource:
    """
    Fetches all 12 Constituent Assembly debate PDF volumes from sansad.in.

    Usage (async context):
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            source = CASource(rate_delay=1.0)
            async for url, content, meta in source.fetch_documents(client):
                # content is bytes (PDF)
                # meta = {"source": "CA", "volume": N}
                ...
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
        """
        Async generator yielding (url, content_bytes, metadata) for each volume.

        Skips volumes disallowed by robots.txt or where the HTTP response
        indicates the document should be skipped (4xx, exhausted 5xx retries).
        Yields nothing for skipped volumes so the caller can count skips separately.
        """
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

    Orchestrates discovery → fetch → parse → segment → canonicalize → index
    for the Constituent Assembly corpus.

    Injects a default CoidHtmlProvider when none is supplied; tests inject a
    custom provider (or use a pre-seeded provider) to control discovery output.
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

            if raw_record.get("date") is None:
                # URL format: https://www.constitutionofindia.net/debates/YYYY-MM-DD
                url_date = doc_ref.fetch_url.rstrip("/").rsplit("/", 1)[-1]
                try:
                    from datetime import date as _date
                    _date.fromisoformat(url_date)  # validate format
                    raw_record["date"] = url_date
                    logger.debug(
                        "ca_orchestrator: extracted date %s from URL for %s",
                        url_date,
                        doc_ref.canonical_doc_id,
                    )
                except ValueError:
                    logger.warning(
                        "ca_orchestrator: could not extract date from URL %s for %s",
                        doc_ref.fetch_url,
                        doc_ref.canonical_doc_id,
                    )

            speeches = segment_speeches(raw_record, source="CA")

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
