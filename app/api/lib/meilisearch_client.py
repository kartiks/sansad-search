from __future__ import annotations

import logging
import os
from typing import Optional

from meilisearch_python_sdk import AsyncClient

logger = logging.getLogger(__name__)

# Seconds to wait for a Meilisearch response before failing the request
# (the search route turns the failure into a 503). Overridable via env.
DEFAULT_TIMEOUT_SECONDS = 5

_client: Optional[AsyncClient] = None


def _timeout_seconds() -> int:
    raw = os.environ.get("MEILISEARCH_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            "Invalid MEILISEARCH_TIMEOUT_SECONDS=%r; using %ss",
            raw, DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    return value


def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(
            os.environ["MEILISEARCH_URL"],
            os.environ["MEILISEARCH_SEARCH_KEY"],
            timeout=_timeout_seconds(),
        )
    return _client


async def close_client() -> None:
    """Close the shared client's HTTP connections (called on API shutdown)."""
    global _client
    if _client is not None:
        client, _client = _client, None
        await client.aclose()
