import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.lib.db import init_pool, close_pool


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
