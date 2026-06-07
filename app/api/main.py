import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.lib.db import init_pool, close_pool
from api.routes import search as search_router
from api.routes import status as status_router
from api.routes import record as record_router
from api.routes import debug as debug_router


def _allowed_origins() -> list:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins if origins else ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="SansadSearch API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(search_router.router)
app.include_router(status_router.router)
app.include_router(record_router.router)
app.include_router(debug_router.router)
