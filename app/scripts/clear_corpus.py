#!/usr/bin/env python3
"""
clear_corpus.py — Remove ingestion data for a corpus from PostgreSQL and Meilisearch.

All checkpoint state now lives in PostgreSQL (processed_documents,
ingestion_dedup_keys) — there is no separate SQLite store. The checkpoint clear is
a PostgreSQL DELETE.

Either --stage or --target must be given (they are mutually exclusive):

  --stage fetch    Clear all stores: PG speeches + qa_exchanges + raw_documents,
                   PG checkpoint tables (processed_documents + ingestion_dedup_keys),
                   Meilisearch. Use before re-fetching from source (forces both
                   Stage 1 and Stage 2 to re-run clean).

  --stage all      Alias for --stage fetch.

  --stage process  Clear Stage 2 output only: PG speeches + qa_exchanges,
                   PG processed_documents (leaves ingestion_dedup_keys and
                   raw_documents intact), Meilisearch. Re-insertion correctness
                   comes from the ON CONFLICT guard after speeches/qa_exchanges are
                   deleted (ARCHITECTURE §8 item 7). Use before re-running
                   segmentation/indexing from existing raw documents.

  --target pg|checkpoints|meili|all
                   Explicit per-store control. --target pg clears all three PG record
                   tables (speeches, qa_exchanges, raw_documents). --target checkpoints
                   clears processed_documents (and ingestion_dedup_keys when no date
                   scope is given). Use when you need precise control over which store
                   is touched.

Usage (run from the app/ directory with the virtualenv active):
    python scripts/clear_corpus.py --corpus ls --stage process --dry-run
    python scripts/clear_corpus.py --corpus ls --stage fetch
    python scripts/clear_corpus.py --corpus ls --stage process --date-from 2024-01-01 --date-to 2024-12-31
    python scripts/clear_corpus.py --corpus all --stage process
    python scripts/clear_corpus.py --corpus rs --target meili
    python scripts/clear_corpus.py --corpus rs --target checkpoints

Environment variables required (per store):
    DATABASE_URL            PostgreSQL DSN  (pg and checkpoints — both are PostgreSQL)
    MEILISEARCH_URL         Meilisearch base URL  (Meilisearch)
    MEILISEARCH_MASTER_KEY  Meilisearch master key  (Meilisearch)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

import httpx
import psycopg2

MEILI_INDEX = "parliamentary_records"
CORPORA = ["CA", "LS", "RS"]


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


def clear_checkpoints(
    corpus: str,
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
    include_dedup_keys: bool,
) -> dict[str, int]:
    """
    Delete checkpoint rows for the corpus from PostgreSQL.

    processed_documents — always cleared for the corpus. When a date range is given,
      the delete joins raw_documents on (canonical_doc_id, corpus) and filters by
      raw_documents.date (this table has no date column). MUST run before any
      raw_documents delete so the join still resolves (the caller orders this
      before clear_pg).
    ingestion_dedup_keys — cleared only when include_dedup_keys is True AND no date
      scope is given. The mirror is not date-scoped (DATA-MODELS §1.7); a date-scoped
      clear touches processed_documents only. Re-insertion correctness after a
      processed_documents-only clear comes from the ON CONFLICT guard (§8 item 7).
    """
    date_scoped = bool(date_from or date_to)
    conn = _pg_connect()
    results: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            # processed_documents
            if date_scoped:
                where = "pd.corpus = %s"
                params: list = [corpus]
                if date_from:
                    where += " AND r.date >= %s"
                    params.append(date_from)
                if date_to:
                    where += " AND r.date <= %s"
                    params.append(date_to)
                if dry_run:
                    cur.execute(
                        "SELECT COUNT(*) FROM processed_documents pd "
                        "JOIN raw_documents r "
                        "  ON pd.canonical_doc_id = r.canonical_doc_id "
                        "  AND pd.corpus = r.corpus "
                        f"WHERE {where}",
                        params,
                    )
                    results["processed_documents"] = cur.fetchone()[0]
                else:
                    cur.execute(
                        "DELETE FROM processed_documents pd "
                        "USING raw_documents r "
                        "WHERE pd.canonical_doc_id = r.canonical_doc_id "
                        "  AND pd.corpus = r.corpus "
                        f"  AND {where}",
                        params,
                    )
                    results["processed_documents"] = cur.rowcount
            else:
                if dry_run:
                    cur.execute(
                        "SELECT COUNT(*) FROM processed_documents WHERE corpus = %s",
                        (corpus,),
                    )
                    results["processed_documents"] = cur.fetchone()[0]
                else:
                    cur.execute(
                        "DELETE FROM processed_documents WHERE corpus = %s", (corpus,)
                    )
                    results["processed_documents"] = cur.rowcount

            # ingestion_dedup_keys — only on a full (non-date-scoped) clear that
            # asks for it (--stage fetch/all, --target checkpoints/all).
            if include_dedup_keys and not date_scoped:
                if dry_run:
                    cur.execute(
                        "SELECT COUNT(*) FROM ingestion_dedup_keys WHERE corpus = %s",
                        (corpus,),
                    )
                    results["ingestion_dedup_keys"] = cur.fetchone()[0]
                else:
                    cur.execute(
                        "DELETE FROM ingestion_dedup_keys WHERE corpus = %s", (corpus,)
                    )
                    results["ingestion_dedup_keys"] = cur.rowcount

        if not dry_run:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return results


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
    # Resolve what to touch from stage semantics or explicit targets.
    # include_dedup_keys gates the ingestion_dedup_keys table (full wipe only):
    # --stage process clears processed_documents but leaves the dedup mirror intact.
    if stage in ("fetch", "all"):
        do_pg, do_checkpoints, do_meili = True, True, True
        include_raw, include_dedup_keys = True, True
    elif stage == "process":
        do_pg, do_checkpoints, do_meili = True, True, True
        include_raw, include_dedup_keys = False, False
    else:
        do_pg = "pg" in targets
        do_checkpoints = "checkpoints" in targets
        do_meili = "meili" in targets
        include_raw = True  # --target pg always includes raw_documents
        include_dedup_keys = True  # --target checkpoints clears both (when no date scope)

    corpora = CORPORA if corpus == "all" else [corpus.upper()]

    for corp in corpora:
        header = f"{'[DRY RUN] ' if dry_run else ''}Corpus {corp}"
        if date_from or date_to:
            header += f"  ({date_from or 'beginning'} → {date_to or 'end'})"
        print(f"\n{header}")

        # Checkpoints first — the date-scoped processed_documents delete joins
        # raw_documents, so it must run before clear_pg removes those rows.
        if do_checkpoints:
            for table, n in clear_checkpoints(
                corp, date_from, date_to, dry_run, include_dedup_keys
            ).items():
                _print_count(f"PG {table}", "rows", n, dry_run)

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
            "Remove ingestion data for a corpus from PostgreSQL and/or Meilisearch. "
            "Run from the app/ directory with the virtualenv active."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
stage semantics:
  --stage fetch    Clears all stores including raw_documents and both checkpoint
                   tables (processed_documents + ingestion_dedup_keys).
                   Use before re-fetching from source (re-runs both Stage 1 and 2).
  --stage all      Alias for --stage fetch.
  --stage process  Clears Stage 2 output only (speeches, qa_exchanges,
                   processed_documents, Meilisearch). Leaves ingestion_dedup_keys
                   and raw_documents intact; re-insertion correctness comes from the
                   ON CONFLICT guard. Use before re-running indexing from raw docs.
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
        choices=["pg", "checkpoints", "meili", "all"],
        help=(
            "Explicit per-store control. pg clears the three PG record tables; "
            "checkpoints clears processed_documents (and ingestion_dedup_keys when "
            "no date scope is given)"
        ),
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
        ["pg", "checkpoints", "meili"] if args.target == "all"
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
