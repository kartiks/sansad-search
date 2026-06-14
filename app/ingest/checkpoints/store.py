"""
PostgreSQL-backed checkpoint store for ingestion resumability and deduplication.

All checkpoint state lives in the Railway PostgreSQL instance alongside
``raw_documents``/``speeches``/``qa_exchanges`` — there is no local SQLite file.
This is what makes the ingestion pipeline deployable as a stateless Railway Cron
Job (DEPLOYMENT §3.7). The two tables are created by ``app/db/schema.sql``
(DATA-MODELS §1.6/§1.7); this module assumes they already exist, exactly as
``indexer.py`` assumes ``speeches``/``qa_exchanges``/``raw_documents`` exist.

Tables:
  processed_documents(
      canonical_doc_id TEXT       NOT NULL,
      corpus           VARCHAR(2) NOT NULL,
      provider         VARCHAR(50),
      fetch_url        TEXT,
      processed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (canonical_doc_id, corpus)
  )
      Stage 2 completion signal. Composite-keyed on (canonical_doc_id, corpus) so
      that LS processing of handle N does not suppress RS processing of the same
      handle N when --source all runs sequentially. A document is added here only
      after ALL its records have been successfully indexed. On resume,
      already-processed documents are skipped (INF-R1).

  ingestion_dedup_keys(
      dedup_key VARCHAR(500) NOT NULL,
      corpus    VARCHAR(2)   NOT NULL,
      PRIMARY KEY (dedup_key, corpus)
  )
      Record-level duplicate PRE-FILTER only. The authoritative duplicate guard is
      the UNIQUE(dedup_key) constraint on speeches/qa_exchanges, enforced via
      INSERT … ON CONFLICT (dedup_key) DO NOTHING (ARCHITECTURE §8 item 7). This
      mirror may safely under-report (a missing entry just means the insert is
      attempted and ON CONFLICT resolves any collision); it must NEVER cause a
      legitimate insert to be skipped. Accordingly the indexer no longer
      short-circuits inserts on this mirror — it is retained only as a cheap
      existence-check surface.

Connection resilience: mirrors indexer.py — a dead server-side connection
(InterfaceError "connection already closed" / OperationalError with no pgcode /
"server closed") triggers a reconnect and one retry. Long Stage 1 discovery/fetch
phases can leave the connection closed by the time a checkpoint write fires.

Usage:
    with CheckpointStore(os.environ["DATABASE_URL"]) as store:
        if store.is_document_processed(canonical_doc_id, corpus="LS"):
            continue
        # … process and index records …
        store.add_dedup_key(dedup_key, corpus="LS")
        store.mark_document_processed(
            canonical_doc_id, corpus="LS", provider="internet_archive",
            fetch_url="https://archive.org/...",
        )
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import psycopg2

logger = logging.getLogger(__name__)


def _is_dead_connection(exc: Exception) -> bool:
    """True when a psycopg2 exception signals a dropped server-side connection.

    Duplicated from indexer.py (rather than imported) to avoid a circular import:
    indexer.py imports CheckpointStore from this module.
    """
    if isinstance(exc, psycopg2.InterfaceError):
        return "connection already closed" in str(exc).lower()
    if not isinstance(exc, psycopg2.OperationalError):
        return False
    pgcode = getattr(exc, "pgcode", None)
    return pgcode is None or "server closed" in str(exc).lower()


def _corpus_from_dedup_key(key: str) -> str:
    """Extract the corpus (source prefix) from a dedup key.

    dedup_key format is ``{source}_{date}_…`` (DATA-MODELS §1.5) where source is
    one of CA/LS/RS, so the leading token is the corpus. Used as a fallback when a
    caller does not pass an explicit corpus to add_dedup_key.
    """
    return key.split("_", 1)[0]


class CheckpointStore:
    """PostgreSQL-backed store for processed documents and inserted dedup keys."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._conn: Optional[Any] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the PostgreSQL connection. Tables are created by schema.sql."""
        self._conn = psycopg2.connect(self.dsn)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "CheckpointStore":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _require_conn(self) -> Any:
        if self._conn is None:
            raise RuntimeError("CheckpointStore is not open — call open() first")
        return self._conn

    def _reconnect(self) -> None:
        """Replace self._conn with a fresh connection using the stored DSN."""
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = psycopg2.connect(self.dsn)
        logger.info("Reconnected to PostgreSQL (checkpoint store) after connection loss")

    def _execute(
        self,
        sql: str,
        params: tuple = (),
        *,
        fetchone: bool = False,
        commit: bool = False,
    ) -> Any:
        """Execute a statement, reconnecting and retrying once on a dead connection.

        Returns the fetched row when ``fetchone`` is set, the affected row count
        when ``commit`` is set (for DELETE/INSERT), else None.
        """
        try:
            return self._run(sql, params, fetchone=fetchone, commit=commit)
        except Exception as exc:
            if _is_dead_connection(exc):
                logger.warning(
                    "Dead PG connection in checkpoint store; reconnecting and retrying"
                )
                self._reconnect()
                return self._run(sql, params, fetchone=fetchone, commit=commit)
            # Non-dead error on a write: roll back so the connection stays usable.
            if commit:
                try:
                    self._require_conn().rollback()
                except psycopg2.InterfaceError:
                    pass
            raise

    def _run(self, sql: str, params: tuple, *, fetchone: bool, commit: bool) -> Any:
        conn = self._require_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        result: Any = None
        if fetchone:
            result = cur.fetchone()
        elif commit:
            result = cur.rowcount
        if commit:
            conn.commit()
        cur.close()
        return result

    # ── Document tracking (processed_documents — Stage 2 complete) ──────────────

    def is_document_processed(self, canonical_doc_id: str, corpus: str) -> bool:
        """Return True if this (canonical_doc_id, corpus) pair was fully processed."""
        row = self._execute(
            "SELECT 1 FROM processed_documents "
            "WHERE canonical_doc_id = %s AND corpus = %s",
            (canonical_doc_id, corpus),
            fetchone=True,
        )
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
        self._execute(
            "INSERT INTO processed_documents "
            "(canonical_doc_id, corpus, provider, fetch_url) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (canonical_doc_id, corpus) DO NOTHING",
            (canonical_doc_id, corpus, provider, fetch_url),
            commit=True,
        )

    def processed_document_count(self) -> int:
        row = self._execute(
            "SELECT COUNT(*) FROM processed_documents", fetchone=True
        )
        return int(row[0])

    def clear_corpus(self, corpus: str) -> int:
        """Delete all processed_documents entries for *corpus*. Returns rows deleted."""
        return int(
            self._execute(
                "DELETE FROM processed_documents WHERE corpus = %s",
                (corpus,),
                commit=True,
            )
        )

    # ── Dedup key tracking (ingestion_dedup_keys — pre-filter only) ─────────────

    def has_dedup_key(self, key: str) -> bool:
        """Return True if *key* was inserted in a prior ingestion run.

        Pre-filter convenience only — NOT consulted by the indexer to skip inserts
        (the UNIQUE(dedup_key) ON CONFLICT guard is authoritative, §8 item 7).
        """
        row = self._execute(
            "SELECT 1 FROM ingestion_dedup_keys WHERE dedup_key = %s",
            (key,),
            fetchone=True,
        )
        return row is not None

    def add_dedup_key(self, key: str, corpus: str | None = None) -> None:
        """Record *key* as inserted. Silently ignores duplicate inserts.

        ``corpus`` defaults to the source prefix embedded in the dedup key
        (DATA-MODELS §1.5) when not supplied.
        """
        corpus = corpus or _corpus_from_dedup_key(key)
        self._execute(
            "INSERT INTO ingestion_dedup_keys (dedup_key, corpus) "
            "VALUES (%s, %s) "
            "ON CONFLICT (dedup_key, corpus) DO NOTHING",
            (key, corpus),
            commit=True,
        )

    def dedup_key_count(self) -> int:
        row = self._execute(
            "SELECT COUNT(*) FROM ingestion_dedup_keys", fetchone=True
        )
        return int(row[0])
