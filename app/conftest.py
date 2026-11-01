import sys
from pathlib import Path

# Make the app/ directory importable as the root, so `ingest.*` and `api.*` resolve.
sys.path.insert(0, str(Path(__file__).parent))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_retry_waits(monkeypatch):
    """Reconnect and Meilisearch retry waits are real sleeps; skip them in tests."""
    import ingest.checkpoints.store as store
    import ingest.indexer as indexer

    monkeypatch.setattr(store, "RECONNECT_DELAYS", ())
    monkeypatch.setattr(indexer, "MEILI_RETRY_DELAYS", ())
