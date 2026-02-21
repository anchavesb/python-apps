"""FastAPI application for dolores-stt."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .engine import STTEngine
from .routes import router as stt_router, set_engine

_engine = STTEngine(
    model_size=settings.model_size,
    device=settings.device,
    compute_type=settings.compute_type,
    cpu_threads=settings.cpu_threads,
    beam_size=settings.beam_size,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("dolores-stt", settings.log_level, json_output=settings.log_format == "json")
    _engine.load()
    set_engine(_engine)
    yield


def _health_details() -> dict:
    return {"model_loaded": _engine.is_loaded, "model_name": settings.model_size}


app = FastAPI(title="dolores-stt", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-stt", "0.1.0", details_fn=_health_details))
app.include_router(stt_router)
