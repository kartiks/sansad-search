"""
Ingestion pipeline CLI entry point.

Usage:
    python -m ingest.main --source ca|ls|rs|all [--date-override YYYY-MM-DD]
    python -m ingest.main --source all --reindex-from-db

Options:
    --source         Which source(s) to ingest: ca, ls, rs, or all
    --date-override  Override the end-date for LS/RS enumeration (YYYY-MM-DD)
    --reindex-from-db  Skip scraping; re-push all PostgreSQL records to Meilisearch

Environment variables required:
    DATABASE_URL        PostgreSQL connection string (psycopg2 DSN)
    MEILISEARCH_URL     Meilisearch Cloud base URL
    MEILISEARCH_MASTER_KEY  Meilisearch master key (for document push)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import httpx
import meilisearch
import psycopg2

from ingest.canonical.names import canonicalize_name, load_names_dict
from ingest.canonical.sessions import canonicalize_session
from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest.parsers.html_parser import parse_html
from ingest.parsers.pdf_parser import parse_pdf
from ingest.segmenters.qa import segment_qa
from ingest.segmenters.speech import segment_speeches
from ingest.sources._http import USER_AGENT
from ingest.sources.ca import CASource
from ingest.sources.ls import LSSource
from ingest.sources.rs import RSSource

logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(__file__).parent.parent / "data" / "ingestion_checkpoints.db"
NAMES_DICT_PATH = Path(__file__).parent.parent / "data" / "names_dict.csv"

# Proceeding types that use the Q+A segmenter
_QA_PROCEEDING_TYPES = frozenset({"starred_question", "unstarred_question"})


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def _connect_postgres() -> Any:
    dsn = os.environ["DATABASE_URL"]
    return psycopg2.connect(dsn)


def _connect_meilisearch() -> Any:
    url = os.environ["MEILISEARCH_URL"]
    key = os.environ["MEILISEARCH_MASTER_KEY"]
    return meilisearch.Client(url, key)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SansadSearch ingestion pipeline"
    )
    parser.add_argument(
        "--source",
        choices=["ca", "ls", "rs", "all"],
        required=True,
        help="Source to ingest (ca | ls | rs | all)",
    )
    parser.add_argument(
        "--date-override",
        metavar="YYYY-MM-DD",
        default=None,
        help="Override end-date for LS/RS scope (optional)",
    )
    parser.add_argument(
        "--reindex-from-db",
        action="store_true",
        default=False,
        help="Skip scraping; re-push all PostgreSQL records to Meilisearch",
    )
    return parser.parse_args(argv)


def _canonicalize_record(
    record: dict[str, Any],
    names_dict: dict[str, str],
) -> dict[str, Any]:
    """Apply name and session canonicalization to a segmenter output record."""
    record = dict(record)
    source = record.get("source", "")

    # Speaker name (speeches)
    if "speaker_name" in record:
        canon, unresolved = canonicalize_name(record["speaker_name"], names_dict)
        record["speaker_name"] = canon
        record["speaker_name_unresolved"] = unresolved

    # Session name
    if "session_name" in record:
        record["session_name"] = canonicalize_session(
            record.get("session_name"), source
        )

    return record


async def _process_document(
    url: str,
    content: Any,        # str (HTML) or bytes (PDF)
    meta: dict[str, Any],
    indexer: Indexer,
    checkpoint: CheckpointStore,
    names_dict: dict[str, str],
    stats: dict[str, int],
) -> None:
    """Parse, segment, canonicalize, and index one document."""
    source: str = meta.get("source", "")
    proceeding_hint: Optional[str] = meta.get("proceeding_type_hint")
    volume: Optional[int] = meta.get("volume")

    # Parse
    try:
        if isinstance(content, bytes):
            raw_record = parse_pdf(
                content,
                source=source,
                source_url=url,
                volume=volume,
                proceeding_type_hint=proceeding_hint,
            )
        else:
            raw_record = parse_html(
                content,
                source=source,
                source_url=url,
                proceeding_type_hint=proceeding_hint,
            )
    except Exception as exc:
        logger.error("Parse error for %s: %s; skipping document", url, exc)
        stats["errors"] += 1
        return

    # Date is required; skip the whole document if missing
    if not raw_record.get("date"):
        logger.error("No parseable date in %s; skipping document", url)
        stats["errors"] += 1
        return

    pt = raw_record.get("proceeding_type") or proceeding_hint or "debate"

    # Segment
    try:
        if pt in _QA_PROCEEDING_TYPES:
            records = segment_qa(raw_record, source, pt)
            record_type = "qa"
        else:
            records = segment_speeches(raw_record, source)
            record_type = "speech"
    except Exception as exc:
        logger.error("Segmentation error for %s: %s; skipping document", url, exc)
        stats["errors"] += 1
        return

    # Canonicalize and index each record
    indexed_this_doc = 0
    for record in records:
        record["record_type"] = record_type
        record = _canonicalize_record(record, names_dict)

        if indexer.index_record(record, checkpoint):
            indexed_this_doc += 1
            logger.info(
                "Indexed: source=%s type=%s date=%s url=%s",
                record.get("source"),
                record.get("proceeding_type"),
                record.get("date"),
                url,
            )
        else:
            stats["skipped"] += 1

    stats["indexed"] += indexed_this_doc
    stats["documents"] += 1
    logger.info(
        "Document processed: %s → %d records indexed", url, indexed_this_doc
    )


async def _run_source(
    source_name: str,
    indexer: Indexer,
    checkpoint: CheckpointStore,
    names_dict: dict[str, str],
    stats: dict[str, int],
    date_override: Optional[date] = None,
) -> None:
    """Fetch and process all documents for one source."""
    http_headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(
        headers=http_headers, timeout=60.0
    ) as client:
        if source_name == "ca":
            source = CASource(rate_delay=1.0)
            gen = source.fetch_documents(client)
        elif source_name == "ls":
            kwargs: dict[str, Any] = {"rate_delay": 1.0}
            if date_override:
                kwargs["date_from"] = date_override
            source = LSSource(**kwargs)
            gen = source.fetch_documents(client)
        else:  # rs
            kwargs = {"rate_delay": 1.0}
            if date_override:
                kwargs["date_from"] = date_override
            source = RSSource(**kwargs)
            gen = source.fetch_documents(client)

        async for url, content, meta in gen:
            if checkpoint.is_url_processed(url):
                logger.info("Already processed %s; skipping", url)
                stats["skipped"] += 1
                continue

            await _process_document(
                url, content, meta, indexer, checkpoint, names_dict, stats
            )
            checkpoint.mark_url_processed(url)

    # Flush remaining Meilisearch batch after source completes
    flushed = indexer.flush()
    if flushed:
        logger.info("Flushed %d documents to Meilisearch", flushed)


async def _async_main(args: argparse.Namespace) -> int:
    """Async main — returns exit code."""
    _setup_logging()

    pg_conn = _connect_postgres()
    meili_client = _connect_meilisearch()
    names_dict = load_names_dict(NAMES_DICT_PATH)
    indexer = Indexer(pg_conn, meili_client)

    # ── Re-index from DB (no scraping) ────────────────────────────────────────
    if args.reindex_from_db:
        logger.info("Reindex mode: reading all records from PostgreSQL")
        total = indexer.reindex_from_db()
        logger.info("Reindex complete: %d documents pushed to Meilisearch", total)
        pg_conn.close()
        return 0

    # ── Normal ingestion ───────────────────────────────────────────────────────
    date_override: Optional[date] = None
    if args.date_override:
        date_override = date.fromisoformat(args.date_override)

    sources = (
        ["ca", "ls", "rs"] if args.source == "all" else [args.source]
    )

    stats: dict[str, int] = {
        "documents": 0, "indexed": 0, "skipped": 0, "errors": 0
    }

    with CheckpointStore(CHECKPOINT_DB) as checkpoint:
        for source_name in sources:
            logger.info("=== Starting source: %s ===", source_name.upper())
            await _run_source(
                source_name, indexer, checkpoint, names_dict, stats, date_override
            )

    # Update index_status table
    try:
        indexer.update_index_status()
    except Exception as exc:
        logger.error("Could not update index_status: %s", exc)

    pg_conn.close()

    # Completion summary
    total = sum(indexer.counts.values())
    logger.info("=== Ingestion complete ===")
    logger.info(
        "  Total indexed: %d  (CA=%d  LS=%d  RS=%d)",
        total,
        indexer.counts.get("CA", 0),
        indexer.counts.get("LS", 0),
        indexer.counts.get("RS", 0),
    )
    logger.info("  Documents processed: %d", stats["documents"])
    logger.info("  Records skipped (duplicates/pre-existing): %d", stats["skipped"])
    logger.info("  Errors: %d", stats["errors"])

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Synchronous entry point: parses args and runs the async pipeline."""
    args = _parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
