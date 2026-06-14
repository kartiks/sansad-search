"""In-memory test double for the checkpoint store.

The real ``CheckpointStore`` (ingest/checkpoints/store.py) is PostgreSQL-only —
psycopg2 + ``DATABASE_URL``. Unit tests that drive the indexer and corpus
orchestrators with *mocked* HTTP/PostgreSQL use this dict-backed fake instead, so
the fast suite needs no database. The real store is exercised against a live
PostgreSQL in ``test_checkpoint_store.py`` (gated on ``TEST_DATABASE_URL``).

The fake implements the full public ``CheckpointStore`` interface and is a drop-in
replacement: ``with FakeCheckpointStore(<anything>) as cp:``. State is keyed by the
constructor argument in a module-level registry, so reopening the *same* key in a
second ``with`` block sees prior state — mirroring how the old SQLite file persisted
across runs. ``Path(":memory:")``/``None`` get fresh instance-local state. pytest's
``tmp_path`` is unique per test, so registry keys never collide across tests.
"""
from __future__ import annotations

from typing import Optional

_REGISTRY: dict[str, dict] = {}


def _is_memory(loc: str) -> bool:
    return loc in ("", "None") or ":memory:" in loc or "memory" in loc.lower()


class FakeCheckpointStore:
    """Dict-backed stand-in for CheckpointStore (same interface, no database)."""

    def __init__(self, location: object = ":memory:") -> None:
        self._loc = str(location)
        if _is_memory(self._loc):
            self._state: dict = {"processed": {}, "dedup": set()}
        else:
            self._state = _REGISTRY.setdefault(
                self._loc, {"processed": {}, "dedup": set()}
            )
        self._open = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def __enter__(self) -> "FakeCheckpointStore":
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _require_open(self) -> None:
        if not self._open:
            raise RuntimeError("CheckpointStore is not open — call open() first")

    @classmethod
    def reset_registry(cls) -> None:
        _REGISTRY.clear()

    # ── Document tracking (processed_documents) ─────────────────────────────────

    def is_document_processed(self, canonical_doc_id: str, corpus: str) -> bool:
        self._require_open()
        return (canonical_doc_id, corpus) in self._state["processed"]

    def mark_document_processed(
        self,
        canonical_doc_id: str,
        corpus: str,
        provider: Optional[str] = None,
        fetch_url: Optional[str] = None,
    ) -> None:
        self._require_open()
        self._state["processed"][(canonical_doc_id, corpus)] = {
            "provider": provider,
            "fetch_url": fetch_url,
        }

    def processed_document_count(self) -> int:
        self._require_open()
        return len(self._state["processed"])

    def clear_corpus(self, corpus: str) -> int:
        self._require_open()
        processed = self._state["processed"]
        keys = [k for k in processed if k[1] == corpus]
        for k in keys:
            del processed[k]
        return len(keys)

    # ── Dedup key tracking (ingestion_dedup_keys — pre-filter only) ─────────────

    def has_dedup_key(self, key: str) -> bool:
        self._require_open()
        return key in self._state["dedup"]

    def add_dedup_key(self, key: str, corpus: Optional[str] = None) -> None:
        self._require_open()
        self._state["dedup"].add(key)

    def dedup_key_count(self) -> int:
        self._require_open()
        return len(self._state["dedup"])
