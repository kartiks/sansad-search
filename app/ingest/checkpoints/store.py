"""
SQLite-backed checkpoint store for ingestion resumability and deduplication.

Tables:
  processed_urls(url TEXT PRIMARY KEY, processed_at TEXT)
      A URL is added here only after ALL its records have been successfully
      indexed. On resume, already-processed URLs are skipped entirely.

  inserted_dedup_keys(dedup_key TEXT PRIMARY KEY)
      Tracks compound dedup keys already written to PostgreSQL for fast
      duplicate detection without issuing a PostgreSQL query per record.

Usage:
    with CheckpointStore(Path("data/ingestion_checkpoints.db")) as store:
        if store.is_url_processed(url):
            continue
        # … process and index records …
        store.add_dedup_key(dedup_key)
        store.mark_url_processed(url)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class CheckpointStore:
    """SQLite-backed store for processed URLs and inserted dedup keys."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open (or create) the SQLite database and ensure schema is present."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_urls (
                url          TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inserted_dedup_keys (
                dedup_key TEXT PRIMARY KEY
            );
        """)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "CheckpointStore":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("CheckpointStore is not open — call open() first")
        return self._conn

    # ── URL tracking ───────────────────────────────────────────────────────────

    def is_url_processed(self, url: str) -> bool:
        """Return True if *url* was fully processed and checkpointed in a prior run."""
        row = self._require_conn().execute(
            "SELECT 1 FROM processed_urls WHERE url = ?", (url,)
        ).fetchone()
        return row is not None

    def mark_url_processed(self, url: str) -> None:
        """
        Record *url* as fully processed.

        Call this only after ALL records from the document have been
        successfully indexed. If indexing is interrupted mid-document,
        do NOT call this — the document will be fully reprocessed on resume.
        """
        conn = self._require_conn()
        conn.execute(
            "INSERT OR REPLACE INTO processed_urls (url, processed_at) VALUES (?, ?)",
            (url, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    # ── Dedup key tracking ─────────────────────────────────────────────────────

    def has_dedup_key(self, key: str) -> bool:
        """Return True if *key* was inserted in a prior ingestion run."""
        row = self._require_conn().execute(
            "SELECT 1 FROM inserted_dedup_keys WHERE dedup_key = ?", (key,)
        ).fetchone()
        return row is not None

    def add_dedup_key(self, key: str) -> None:
        """Record *key* as inserted. Silently ignores duplicate inserts."""
        conn = self._require_conn()
        conn.execute(
            "INSERT OR IGNORE INTO inserted_dedup_keys (dedup_key) VALUES (?)",
            (key,),
        )
        conn.commit()

    # ── Counters (useful for tests and progress reporting) ─────────────────────

    def processed_url_count(self) -> int:
        return self._require_conn().execute(
            "SELECT COUNT(*) FROM processed_urls"
        ).fetchone()[0]

    def dedup_key_count(self) -> int:
        return self._require_conn().execute(
            "SELECT COUNT(*) FROM inserted_dedup_keys"
        ).fetchone()[0]
