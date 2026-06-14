"""
Ingestion pipeline CLI entry point.

Usage:
    python -m ingest.main --source ca|ls|rs|all [--stage fetch|process|all]
    python -m ingest.main --source all --stage process --date-from 2024-01-01 --date-to 2024-12-31
    python -m ingest.main --source all --reindex-from-db

Options:
    --source         Which source(s) to ingest: ca, ls, rs, or all
    --stage          Pipeline stage to run (default: all)
                       fetch   — Stage 1 only: discover + fetch + parse → raw_documents
                       process — Stage 2 only: segment + index from raw_documents
                       all     — Stage 1 then Stage 2
    --date-from      Both-stage scope: only fetch/process raw_documents rows on/after this date
    --date-to        Both-stage scope: only fetch/process raw_documents rows on/before this date
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
import meilisearch_python_sdk as meilisearch
import psycopg2

from ingest.canonical.names import load_names_dict
from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer
from ingest.sources._http import USER_AGENT
from ingest.sources.ca import CAOrchestrator
from ingest.sources.ls import LSOrchestrator
from ingest.sources.rs import RSOrchestrator

logger = logging.getLogger(__name__)

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
        "--stage",
        choices=["fetch", "process", "all"],
        default="all",
        help="Pipeline stage: fetch (Stage 1 only), process (Stage 2 only), or all (default)",
    )
    parser.add_argument(
        "--date-from",
        metavar="YYYY-MM-DD",
        default=None,
        help="Both-stage scope: fetch/process raw_documents rows on/after this date (optional)",
    )
    parser.add_argument(
        "--date-to",
        metavar="YYYY-MM-DD",
        default=None,
        help="Both-stage scope: fetch/process raw_documents rows on/before this date (optional)",
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
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Any:
    """Build the orchestrator for one source."""
    if source_name == "ca":
        return CAOrchestrator(client, checkpoint, indexer, names_dict, date_from=date_from, date_to=date_to)
    if source_name == "ls":
        return LSOrchestrator(client, checkpoint, indexer, names_dict, date_from=date_from, date_to=date_to)
    if source_name == "rs":
        return RSOrchestrator(client, checkpoint, indexer, names_dict, date_from=date_from, date_to=date_to)
    raise ValueError(f"Unknown source: {source_name}")


async def _async_main(args: argparse.Namespace) -> int:
    """Async main — returns exit code."""
    _setup_logging()

    pg_dsn = os.environ["DATABASE_URL"]
    pg_conn = _connect_postgres()
    meili_client = _connect_meilisearch()
    names_dict = load_names_dict(NAMES_DICT_PATH)
    indexer = Indexer(pg_conn, meili_client, pg_dsn=pg_dsn)

    # ── Re-index from DB (no scraping) ────────────────────────────────────────
    if args.reindex_from_db:
        logger.info("Reindex mode: reading all records from PostgreSQL")
        total = indexer.reindex_from_db()
        logger.info("Reindex complete: %d documents pushed to Meilisearch", total)
        pg_conn.close()
        return 0

    # ── Validate date args ────────────────────────────────────────────────────
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    if args.date_from:
        date.fromisoformat(args.date_from)  # raises ValueError on bad input
        date_from = args.date_from
    if args.date_to:
        date.fromisoformat(args.date_to)
        date_to = args.date_to

    sources = ["ca", "ls", "rs"] if args.source == "all" else [args.source]
    stage = args.stage

    stage1_stats: dict[str, int] = {"fetched": 0, "skipped": 0, "errors": 0}
    stage2_stats: dict[str, int] = {"indexed": 0, "skipped": 0, "errors": 0}

    http_headers = {"User-Agent": USER_AGENT}
    with CheckpointStore(pg_dsn) as checkpoint:
        async with httpx.AsyncClient(headers=http_headers, timeout=60.0) as client:
            for source_name in sources:
                logger.info("=== Starting source: %s ===", source_name.upper())
                orchestrator = _make_orchestrator(
                    source_name, client, checkpoint, indexer, names_dict,
                    date_from=date_from, date_to=date_to,
                )

                if stage in ("fetch", "all"):
                    logger.info("--- Stage 1 (fetch): %s ---", source_name.upper())
                    s1 = await orchestrator.run_stage1(date_from=date_from, date_to=date_to)
                    for k in stage1_stats:
                        stage1_stats[k] += s1.get(k, 0)

                if stage in ("process", "all"):
                    logger.info("--- Stage 2 (process): %s ---", source_name.upper())
                    s2 = await orchestrator.run_stage2(
                        date_from=date_from, date_to=date_to
                    )
                    for k in stage2_stats:
                        stage2_stats[k] += s2.get(k, 0)

    # Flush any remaining buffered Meilisearch documents (Stage 2 only)
    if stage in ("process", "all"):
        indexer.flush()
        try:
            indexer.update_index_status()
        except Exception as exc:
            logger.error("Could not update index_status: %s", exc)

    pg_conn.close()

    # Completion summary
    logger.info("=== Ingestion complete ===")
    if stage in ("fetch", "all"):
        logger.info(
            "  Stage 1 (fetch) — documents written to raw_documents: %d  "
            "(skipped=%d  errors=%d)",
            stage1_stats["fetched"],
            stage1_stats["skipped"],
            stage1_stats["errors"],
        )
    if stage in ("process", "all"):
        total = sum(indexer.counts.values())
        logger.info(
            "  Stage 2 (process) — records indexed: %d  (CA=%d  LS=%d  RS=%d)",
            total,
            indexer.counts.get("CA", 0),
            indexer.counts.get("LS", 0),
            indexer.counts.get("RS", 0),
        )
        logger.info(
            "  Records indexed (this run): %d", stage2_stats["indexed"]
        )
        logger.info(
            "  Records skipped (already processed): %d", stage2_stats["skipped"]
        )
        logger.info("  Errors: %d", stage2_stats["errors"])

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """Synchronous entry point: parses args and runs the async pipeline."""
    args = _parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
