"""
SQLite-backed checkpoint store for ingestion resumability and deduplication.

Tables:
  processed_documents(
      canonical_doc_id TEXT NOT NULL,
      corpus           TEXT NOT NULL,
      provider         TEXT,
      fetch_url        TEXT,
      processed_at     TEXT NOT NULL,
      PRIMARY KEY (canonical_doc_id, corpus)
  )
      Composite-keyed on (canonical_doc_id, corpus) so that LS processing of
      handle N does not suppress RS processing of the same handle N when
      --source all runs sequentially. A document is added here only after ALL
      its records have been successfully indexed. On resume, already-processed
      documents are skipped. provider/fetch_url record which provider satisfied
      the document for audit.

  inserted_dedup_keys(dedup_key TEXT PRIMARY KEY)
      Tracks compound dedup keys already written to PostgreSQL for fast
      duplicate detection without issuing a PostgreSQL query per record.

Usage:
    with CheckpointStore(Path("data/ingestion_checkpoints.db")) as store:
        if store.is_document_processed(canonical_doc_id, corpus="LS"):
            continue
        # … process and index records …
        store.add_dedup_key(dedup_key)
        store.mark_document_processed(
            canonical_doc_id, corpus="LS", provider="internet_archive",
            fetch_url="https://archive.org/...",
        )
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class CheckpointStore:
    """SQLite-backed store for processed documents and inserted dedup keys."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open (or create) the SQLite database and ensure schema is present."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_documents (
                canonical_doc_id TEXT NOT NULL,
                corpus           TEXT NOT NULL,
                provider         TEXT,
                fetch_url        TEXT,
                processed_at     TEXT NOT NULL,
                PRIMARY KEY (canonical_doc_id, corpus)
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

    # ── Document tracking ──────────────────────────────────────────────────────

    def is_document_processed(self, canonical_doc_id: str, corpus: str) -> bool:
        """Return True if this (canonical_doc_id, corpus) pair was fully processed."""
        row = self._require_conn().execute(
            "SELECT 1 FROM processed_documents WHERE canonical_doc_id = ? AND corpus = ?",
            (canonical_doc_id, corpus),
        ).fetchone()
        return row is not None

    def mark_document_processed(
        self,
        canonical_doc_id: str,
        corpus: str,
        provider: str | None = None,
        fetch_url: str | None = None,
    ) -> None:
        """
        Record this document as fully processed.

        Call only after ALL records from the document have been successfully
        indexed. If indexing is interrupted mid-document, do NOT call this —
        the document will be fully reprocessed on resume.
        """
        conn = self._require_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO processed_documents
                (canonical_doc_id, corpus, provider, fetch_url, processed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                canonical_doc_id,
                corpus,
                provider,
                fetch_url,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

    def processed_document_count(self) -> int:
        return self._require_conn().execute(
            "SELECT COUNT(*) FROM processed_documents"
        ).fetchone()[0]

    def clear_corpus(self, corpus: str) -> int:
        """Delete all processed_documents entries for *corpus*. Returns the count deleted."""
        conn = self._require_conn()
        cursor = conn.execute(
            "DELETE FROM processed_documents WHERE corpus = ?", (corpus,)
        )
        conn.commit()
        return cursor.rowcount

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

    def dedup_key_count(self) -> int:
        return self._require_conn().execute(
            "SELECT COUNT(*) FROM inserted_dedup_keys"
        ).fetchone()[0]
