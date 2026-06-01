"""
Ingestion pipeline CLI entry point.

Usage:
    python -m ingest.main --source ca|ls|rs|all [--date-override YYYY-MM-DD]
    python -m ingest.main --source all --reindex-from-db

Options:
    --source         Which source(s) to ingest: ca, ls, rs, or all
    --date-override  Scope LS/RS ingestion to documents on/after this date
                     (YYYY-MM-DD). Forwarded to the orchestrators as date_from.
    --reindex-from-db  Skip scraping; re-push all PostgreSQL records to Meilisearch

Environment variables required:
    DATABASE_URL        PostgreSQL connection string (psycopg2 DSN)
    MEILISEARCH_URL     Meilisearch Cloud base URL
    MEILISEARCH_MASTER_KEY  Meilisearch master key (for document push)

Each source is handled by a dedicated orchestrator (Phase 8/9). The
orchestrators own discovery, fetching, parsing, segmentation,
canonicalization, indexing, and their own per-document checkpoint
interactions (keyed by canonical_doc_id). This entry point only selects the
orchestrator(s), drives them with a shared HTTP client, and aggregates the
stats they return.
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

from ingest.canonical.names import load_names_dict
from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest.sources._http import USER_AGENT
from ingest.sources.ca import CAOrchestrator
from ingest.sources.ls import LSOrchestrator
from ingest.sources.rs import RSOrchestrator

logger = logging.getLogger(__name__)

CHECKPOINT_DB = Path(__file__).parent.parent / "data" / "ingestion_checkpoints.db"
NAMES_DICT_PATH = Path(__file__).parent.parent / "data" / "names_dict.csv"


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
        help="Scope LS/RS ingestion to documents on/after this date (optional)",
    )
    parser.add_argument(
        "--reindex-from-db",
        action="store_true",
        default=False,
        help="Skip scraping; re-push all PostgreSQL records to Meilisearch",
    )
    return parser.parse_args(argv)


def _make_orchestrator(
    source_name: str,
    client: httpx.AsyncClient,
    checkpoint: CheckpointStore,
    indexer: Indexer,
    names_dict: dict[str, str],
    date_override: Optional[str],
) -> Any:
    """Build the orchestrator for one source.

    The shared HTTP client is injected at construction. ``--date-override`` is
    wired into LS and RS via their ``date_from`` constructor parameter (which
    forwards it to the date-filterable providers); CA has no date-scoped
    enumeration so it ignores the override.
    """
    if source_name == "ca":
        return CAOrchestrator(client, checkpoint, indexer, names_dict)
    if source_name == "ls":
        return LSOrchestrator(
            client, checkpoint, indexer, names_dict, date_from=date_override
        )
    if source_name == "rs":
        return RSOrchestrator(
            client, checkpoint, indexer, names_dict, date_from=date_override
        )
    raise ValueError(f"Unknown source: {source_name}")


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
    # date_override is the ISO YYYY-MM-DD string passed straight through to the
    # orchestrators (and on to their date-scoped providers, which consume the
    # string form). Validate the format here so a malformed value fails fast.
    date_override: Optional[str] = None
    if args.date_override:
        date.fromisoformat(args.date_override)  # raises ValueError on bad input
        date_override = args.date_override

    sources = (
        ["ca", "ls", "rs"] if args.source == "all" else [args.source]
    )

    stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

    http_headers = {"User-Agent": USER_AGENT}
    with CheckpointStore(CHECKPOINT_DB) as checkpoint:
        async with httpx.AsyncClient(
            headers=http_headers, timeout=60.0
        ) as client:
            for source_name in sources:
                logger.info("=== Starting source: %s ===", source_name.upper())
                orchestrator = _make_orchestrator(
                    source_name, client, checkpoint, indexer, names_dict,
                    date_override,
                )
                source_stats = await orchestrator.run()
                for key in stats:
                    stats[key] += source_stats.get(key, 0)

    # Flush any remaining buffered Meilisearch documents
    indexer.flush()

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
    logger.info("  Records indexed (this run): %d", stats["indexed"])
    logger.info("  Records skipped (duplicates/pre-existing): %d", stats["skipped"])
    logger.info("  Errors: %d", stats["errors"])

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Synchronous entry point: parses args and runs the async pipeline."""
    args = _parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
