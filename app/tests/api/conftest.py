"""
Shared fixtures for API route tests.

All tests use dependency overrides so no real DB or Meilisearch connections
are required.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client


# ── Pool / asyncpg helpers ────────────────────────────────────────────────────

def make_mock_pool(
    fetchrow_result: Any = None,
    fetchrow_side_effect: Any = None,
    fetch_result: Any = None,
    fetch_side_effect: Any = None,
) -> MagicMock:
    """
    Build a mock asyncpg pool whose acquire() context manager returns a
    connection with configurable fetchrow() and fetch() methods.
    """
    mock_conn = AsyncMock()

    if fetchrow_side_effect is not None:
        mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    else:
        mock_conn.fetchrow = AsyncMock(return_value=fetchrow_result)

    if fetch_side_effect is not None:
        mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
    elif fetch_result is not None:
        mock_conn.fetch = AsyncMock(return_value=fetch_result)
    else:
        mock_conn.fetch = AsyncMock(return_value=[])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


# ── Meilisearch helpers ───────────────────────────────────────────────────────

_DEFAULT_MEILI_RESPONSE: Dict[str, Any] = {
    "hits": [],
    "totalHits": 0,
    "totalPages": 0,
    "page": 1,
    "hitsPerPage": 20,
}

# camelCase → snake_case mapping for the keys search.py accesses as attributes
_MEILI_KEY_MAP: Dict[str, str] = {
    "totalHits": "total_hits",
    "totalPages": "total_pages",
    "hitsPerPage": "hits_per_page",
}


def _meili_dict_to_ns(d: Dict[str, Any]) -> SimpleNamespace:
    """
    Convert a camelCase Meilisearch response dict to an attribute-accessible
    SimpleNamespace.  search.py accesses results via attribute lookup
    (raw.hits, raw.total_hits, …) so the mock must return an object that
    supports that, not a plain dict.
    """
    return SimpleNamespace(**{_MEILI_KEY_MAP.get(k, k): v for k, v in d.items()})


def make_mock_meili_client(
    search_result: Optional[Dict[str, Any]] = None,
    search_side_effect: Any = None,
) -> MagicMock:
    """
    Build a mock meilisearch.AsyncClient whose index("parliamentary_records")
    returns an async index with a configurable search().

    search() returns a SimpleNamespace (not a plain dict) so that
    attribute-style access used in search.py (raw.hits, raw.total_hits, …)
    works correctly.
    """
    mock_index = AsyncMock()
    if search_side_effect is not None:
        mock_index.search = AsyncMock(side_effect=search_side_effect)
    else:
        result_ns = _meili_dict_to_ns(search_result or dict(_DEFAULT_MEILI_RESPONSE))
        mock_index.search = AsyncMock(return_value=result_ns)

    mock_client = MagicMock()
    mock_client.index = MagicMock(return_value=mock_index)
    return mock_client


# ── TestClient fixture ────────────────────────────────────────────────────────

@pytest.fixture
def mock_pool() -> MagicMock:
    return make_mock_pool()


@pytest.fixture
def mock_meili() -> MagicMock:
    return make_mock_meili_client()


@pytest.fixture
def test_client(mock_pool: MagicMock, mock_meili: MagicMock) -> TestClient:
    """
    TestClient with dependency overrides for pool and meilisearch client.
    lifespan init_pool / close_pool are patched to no-ops.
    """
    from unittest.mock import patch

    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_client] = lambda: mock_meili

    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()
