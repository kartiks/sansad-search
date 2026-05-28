from __future__ import annotations

import os
import meilisearch
from typing import Optional

_client: Optional[meilisearch.AsyncClient] = None


def get_client() -> meilisearch.AsyncClient:
    global _client
    if _client is None:
        _client = meilisearch.AsyncClient(
            os.environ["MEILISEARCH_URL"],
            os.environ["MEILISEARCH_SEARCH_KEY"],
        )
    return _client
