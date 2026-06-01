from __future__ import annotations

import os
from typing import Optional
from meilisearch_python_sdk import AsyncClient

_client: Optional[AsyncClient] = None


def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(
            os.environ["MEILISEARCH_URL"],
            os.environ["MEILISEARCH_SEARCH_KEY"],
        )
    return _client
