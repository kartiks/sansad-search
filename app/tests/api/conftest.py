"""
Shared fixtures for API route tests.

All tests use dependency overrides so no real DB or Meilisearch connections
are required.
"""
from __future__ import annotations

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
) -> MagicMock:
    """
    Build a mock asyncpg pool whose acquire() context manager returns a
    connection with a configurable fetchrow().
    """
    mock_conn = AsyncMock()
    if fetchrow_side_effect is not None:
        mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    else:
        mock_conn.fetchrow = AsyncMock(return_value=fetchrow_result)

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


def make_mock_meili_client(
    search_result: Optional[Dict[str, Any]] = None,
    search_side_effect: Any = None,
) -> MagicMock:
    """
    Build a mock meilisearch.AsyncClient whose index("parliamentary_records")
    returns an async index with a configurable search().
    """
    mock_index = AsyncMock()
    if search_side_effect is not None:
        mock_index.search = AsyncMock(side_effect=search_side_effect)
    else:
        mock_index.search = AsyncMock(
            return_value=search_result or dict(_DEFAULT_MEILI_RESPONSE)
        )

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
