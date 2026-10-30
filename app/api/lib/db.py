from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


class DatabaseUnavailableError(RuntimeError):
    """Raised when the connection pool is not available."""


# Errors that mean the database could not serve the request (outage, dropped
# connection, pool timeout, server-side failure). Routes map these to 503.
# Anything else is a bug and is left to surface as a 500.
DB_ERRORS = (
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
    OSError,
    asyncio.TimeoutError,
    DatabaseUnavailableError,
)

DB_UNAVAILABLE_BODY = {
    "error": "database_unavailable",
    "message": "The database is temporarily unavailable.",
}


def is_valid_uuid(value: str) -> bool:
    """True when *value* parses as a UUID (record ids are UUID primary keys)."""
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise DatabaseUnavailableError("Database pool not initialised")
    return _pool
