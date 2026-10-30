import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.lib.db import (
    DB_UNAVAILABLE_BODY,
    DatabaseUnavailableError,
    close_pool,
    init_pool,
)
from api.lib.meilisearch_client import close_client
from api.routes import search as search_router
from api.routes import status as status_router
from api.routes import record as record_router
from api.routes import debug as debug_router

logger = logging.getLogger(__name__)


def _allowed_origins() -> list:
    """
    Parse ALLOWED_ORIGINS (comma-separated). Fails closed: when unset or
    empty, no cross-origin requests are allowed. Same-origin traffic (the
    Vercel /api rewrite and the Vite dev proxy) does not need CORS.
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        logger.warning(
            "ALLOWED_ORIGINS is not set: cross-origin requests to the API "
            "will be rejected. Set it to a comma-separated list of origins."
        )
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    try:
        yield
    finally:
        await close_client()
        await close_pool()


app = FastAPI(title="SansadSearch API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseUnavailableError)
async def _database_unavailable(request: Request, exc: DatabaseUnavailableError):
    # Raised by the get_pool dependency when the pool was never initialised.
    logger.error("Database pool unavailable for %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content=DB_UNAVAILABLE_BODY)


app.include_router(search_router.router)
app.include_router(status_router.router)
app.include_router(record_router.router)
app.include_router(debug_router.router)
