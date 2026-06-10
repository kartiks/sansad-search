#!/usr/bin/env python3
"""
clear_corpus.py — Remove ingestion data for a corpus from PG, SQLite, and Meilisearch.

Either --stage or --target must be given (they are mutually exclusive):

  --stage fetch    Clear all stores: PG speeches + qa_exchanges + raw_documents,
                   SQLite processed_documents, Meilisearch. Use before re-fetching
                   from source (forces both Stage 1 and Stage 2 to re-run clean).

  --stage all      Alias for --stage fetch.

  --stage process  Clear Stage 2 output only: PG speeches + qa_exchanges,
                   SQLite processed_documents, Meilisearch. Leaves raw_documents
                   intact. Use before re-running segmentation/indexing from existing
                   raw documents.

  --target pg|sqlite|meili|all
                   Explicit per-store control. --target pg clears all three PG tables
                   (speeches, qa_exchanges, raw_documents). Use when you need precise
                   control over which store is touched.

Usage (run from the app/ directory with the virtualenv active):
    python scripts/clear_corpus.py --corpus ls --stage process --dry-run
    python scripts/clear_corpus.py --corpus ls --stage fetch
    python scripts/clear_corpus.py --corpus ls --stage process --date-from 2024-01-01 --date-to 2024-12-31
    python scripts/clear_corpus.py --corpus all --stage process
    python scripts/clear_corpus.py --corpus rs --target meili

Environment variables required (per store):
    DATABASE_URL            PostgreSQL DSN  (PG; also SQLite when --date-from/--date-to used)
    MEILISEARCH_URL         Meilisearch base URL  (Meilisearch)
    MEILISEARCH_MASTER_KEY  Meilisearch master key  (Meilisearch)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import psycopg2

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "ingestion_checkpoints.db"
MEILI_INDEX = "parliamentary_records"
CORPORA = ["CA", "LS", "RS"]
_SQLITE_CHUNK = 900  # stay under SQLite's 999-placeholder limit


# ── Env / connection helpers ───────────────────────────────────────────────────

def _require_env(*names: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Error: missing required environment variable(s): {', '.join(missing)}")


def _pg_connect():
    _require_env("DATABASE_URL")
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _meili_headers() -> dict[str, str]:
    _require_env("MEILISEARCH_URL", "MEILISEARCH_MASTER_KEY")
    return {
        "Authorization": f"Bearer {os.environ['MEILISEARCH_MASTER_KEY']}",
        "Content-Type": "application/json",
    }


def _meili_base() -> str:
    return os.environ["MEILISEARCH_URL"].rstrip("/")


# ── Meilisearch helpers ────────────────────────────────────────────────────────

def _meili_wait_task(task_uid: int, base: str, headers: dict, timeout: int = 300) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = httpx.get(f"{base}/tasks/{task_uid}", headers=headers, timeout=10)
        resp.raise_for_status()
        task = resp.json()
        if task["status"] in ("succeeded", "failed", "canceled"):
            return task
        time.sleep(2)
    raise TimeoutError(f"Meilisearch task {task_uid} did not complete within {timeout}s")


def _build_meili_filter(corpus: str, date_from: str | None, date_to: str | None) -> str:
    parts = [f'source = "{corpus}"']
    if date_from:
        parts.append(f'date >= "{date_from}"')
    if date_to:
        parts.append(f'date <= "{date_to}"')
    return " AND ".join(parts)


# ── Per-store clear functions ──────────────────────────────────────────────────

def clear_pg(
    corpus: str,
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
    include_raw: bool = True,
) -> dict[str, int]:
    """
    Delete from PG for the corpus + date scope.

    include_raw=True  — clears speeches, qa_exchanges, raw_documents
                        (--stage fetch / --target pg / --target all)
    include_raw=False — clears speeches, qa_exchanges only, leaving raw_documents intact
                        (--stage process)
    """
    tables = [("speeches", "source"), ("qa_exchanges", "source")]
    if include_raw:
        tables.append(("raw_documents", "corpus"))

    conn = _pg_connect()
    results: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            for table, col in tables:
                params: list = [corpus]
                where = f"{col} = %s"
                if date_from:
                    where += " AND date >= %s"
                    params.append(date_from)
                if date_to:
                    where += " AND date <= %s"
                    params.append(date_to)

                if dry_run:
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params)
                    results[table] = cur.fetchone()[0]
                else:
                    cur.execute(f"DELETE FROM {table} WHERE {where}", params)
                    results[table] = cur.rowcount

        if not dry_run:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return results


def _get_canonical_ids(
    corpus: str,
    date_from: str | None,
    date_to: str | None,
) -> list[str]:
    """Query PG raw_documents for canonical_doc_ids matching the corpus + date scope."""
    conn = _pg_connect()
    try:
        params: list = [corpus]
        where = "corpus = %s"
        if date_from:
            where += " AND date >= %s"
            params.append(date_from)
        if date_to:
            where += " AND date <= %s"
            params.append(date_to)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT canonical_doc_id FROM raw_documents WHERE {where}", params
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def clear_sqlite(
    corpus: str,
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
    canonical_ids: list[str] | None = None,
) -> dict[str, int]:
    """
    Delete processed_documents rows for the corpus, optionally scoped by date.

    canonical_ids — pre-fetched from PG raw_documents. Pass these when PG's
    raw_documents will be cleared in the same run (avoids an empty lookup after
    the PG delete). If None and a date range is given, the lookup is done here.
    """
    import sqlite3

    if not SQLITE_PATH.exists():
        print(f"  SQLite: {SQLITE_PATH} not found — skipping")
        return {"processed_documents": 0}

    if date_from or date_to:
        if canonical_ids is None:
            canonical_ids = _get_canonical_ids(corpus, date_from, date_to)
        if not canonical_ids:
            return {"processed_documents": 0}

        total = 0
        conn = sqlite3.connect(str(SQLITE_PATH))
        try:
            for i in range(0, len(canonical_ids), _SQLITE_CHUNK):
                chunk = canonical_ids[i : i + _SQLITE_CHUNK]
                placeholders = ",".join("?" * len(chunk))
                params = chunk + [corpus]
                if dry_run:
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM processed_documents "
                        f"WHERE canonical_doc_id IN ({placeholders}) AND corpus = ?",
                        params,
                    ).fetchone()
                    total += row[0]
                else:
                    cur = conn.execute(
                        f"DELETE FROM processed_documents "
                        f"WHERE canonical_doc_id IN ({placeholders}) AND corpus = ?",
                        params,
                    )
                    total += cur.rowcount
            if not dry_run:
                conn.commit()
        finally:
            conn.close()
        return {"processed_documents": total}

    # No date scope — clear all processed_documents for the corpus
    conn = sqlite3.connect(str(SQLITE_PATH))
    try:
        if dry_run:
            row = conn.execute(
                "SELECT COUNT(*) FROM processed_documents WHERE corpus = ?", (corpus,)
            ).fetchone()
            count = row[0]
        else:
            cur = conn.execute(
                "DELETE FROM processed_documents WHERE corpus = ?", (corpus,)
            )
            conn.commit()
            count = cur.rowcount
    finally:
        conn.close()
    return {"processed_documents": count}


def clear_meili(
    corpus: str,
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
) -> dict[str, int]:
    """Delete Meilisearch documents for the corpus using the delete-by-filter API."""
    base = _meili_base()
    headers = _meili_headers()
    meili_filter = _build_meili_filter(corpus, date_from, date_to)

    if dry_run:
        resp = httpx.post(
            f"{base}/indexes/{MEILI_INDEX}/search",
            headers=headers,
            json={"filter": meili_filter, "limit": 0},
            timeout=15,
        )
        resp.raise_for_status()
        count = resp.json().get("estimatedTotalHits", 0)
        return {"documents (estimated)": count}

    resp = httpx.post(
        f"{base}/indexes/{MEILI_INDEX}/documents/delete",
        headers=headers,
        json={"filter": meili_filter},
        timeout=15,
    )
    resp.raise_for_status()
    task_uid = resp.json()["taskUid"]
    print(f"  Meilisearch: task {task_uid} enqueued — polling for completion...")
    task = _meili_wait_task(task_uid, base, headers)
    if task["status"] != "succeeded":
        raise RuntimeError(
            f"Meilisearch task {task_uid} {task['status']}: {task.get('error')}"
        )
    deleted = task.get("details", {}).get("deletedDocuments", 0)
    return {"documents": deleted}


# ── Orchestration ──────────────────────────────────────────────────────────────

def _print_count(store: str, key: str, count: int, dry_run: bool) -> None:
    verb = "Would delete" if dry_run else "Deleted"
    suffix = f" {key}" if key else ""
    print(f"  {store}: {verb} {count}{suffix}")


def run(
    corpus: str,
    stage: str | None,
    targets: list[str],
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
) -> None:
    # Resolve what to touch from stage semantics or explicit targets
    if stage in ("fetch", "all"):
        do_pg, do_sqlite, do_meili, include_raw = True, True, True, True
    elif stage == "process":
        do_pg, do_sqlite, do_meili, include_raw = True, True, True, False
    else:
        do_pg = "pg" in targets
        do_sqlite = "sqlite" in targets
        do_meili = "meili" in targets
        include_raw = True  # --target pg always includes raw_documents

    corpora = CORPORA if corpus == "all" else [corpus.upper()]

    for corp in corpora:
        header = f"{'[DRY RUN] ' if dry_run else ''}Corpus {corp}"
        if date_from or date_to:
            header += f"  ({date_from or 'beginning'} → {date_to or 'end'})"
        print(f"\n{header}")

        # Pre-fetch canonical_ids from raw_documents before any PG deletions.
        # When --stage fetch is used with a date range, PG will clear raw_documents,
        # so the SQLite lookup must happen first against the still-intact table.
        canonical_ids: list[str] | None = None
        if do_sqlite and (date_from or date_to):
            canonical_ids = _get_canonical_ids(corp, date_from, date_to)

        # SQLite first — uses pre-fetched IDs, so the PG step can safely clear
        # raw_documents without breaking the date-scoped SQLite delete.
        if do_sqlite:
            for table, n in clear_sqlite(
                corp, date_from, date_to, dry_run, canonical_ids
            ).items():
                _print_count(f"SQLite {table}", "rows", n, dry_run)

        if do_pg:
            for table, n in clear_pg(
                corp, date_from, date_to, dry_run, include_raw
            ).items():
                _print_count(f"PG {table}", "rows", n, dry_run)

        if do_meili:
            for label, n in clear_meili(corp, date_from, date_to, dry_run).items():
                _print_count(f"Meilisearch {label}", "", n, dry_run)


# ── Entry point ────────────────────────────────────────────────────────────────

def _valid_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Not a valid date (YYYY-MM-DD): {value!r}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove ingestion data for a corpus from PG, SQLite, and/or Meilisearch. "
            "Run from the app/ directory with the virtualenv active."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
stage semantics:
  --stage fetch    Clears all stores including raw_documents.
                   Use before re-fetching from source (re-runs both Stage 1 and 2).
  --stage all      Alias for --stage fetch.
  --stage process  Clears Stage 2 output only (speeches, qa_exchanges,
                   processed_documents, Meilisearch). Leaves raw_documents intact.
                   Use before re-running segmentation/indexing from existing raw docs.
""",
    )
    parser.add_argument(
        "--corpus",
        required=True,
        choices=["ca", "ls", "rs", "all"],
        help="Corpus to clear (case-insensitive)",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--stage",
        choices=["fetch", "all", "process"],
        help=(
            "'fetch'/'all' clears all stores; "
            "'process' clears Stage 2 output only (leaves raw_documents intact)"
        ),
    )
    mode.add_argument(
        "--target",
        choices=["pg", "sqlite", "meili", "all"],
        help="Explicit per-store control (pg clears all three PG tables)",
    )

    parser.add_argument(
        "--date-from",
        type=_valid_date,
        metavar="YYYY-MM-DD",
        help="Clear records from this date (inclusive)",
    )
    parser.add_argument(
        "--date-to",
        type=_valid_date,
        metavar="YYYY-MM-DD",
        help="Clear records up to this date (inclusive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts without deleting anything",
    )
    args = parser.parse_args()

    targets = (
        ["pg", "sqlite", "meili"] if args.target == "all"
        else [args.target] if args.target
        else []
    )
    run(
        corpus=args.corpus,
        stage=args.stage,
        targets=targets,
        date_from=args.date_from,
        date_to=args.date_to,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
