"""FastAPI application for dolores-stt."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .engine import STTEngine
from .routes import router as stt_router
from .routes import set_engine, set_speaker_identifier

_engine = STTEngine(
    model_size=settings.model_size,
    device=settings.device,
    compute_type=settings.compute_type,
    cpu_threads=settings.cpu_threads,
    beam_size=settings.beam_size,
)

_speaker_id = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _speaker_id
    setup_logging("dolores-stt", settings.log_level, json_output=settings.log_format == "json")
    _engine.load()
    set_engine(_engine)

    if settings.speaker_id_enabled:
        from .speaker import SpeakerIdentifier

        _speaker_id = SpeakerIdentifier(
            db_path=settings.speaker_db_path,
            threshold=settings.speaker_threshold,
        )
        _speaker_id.load()
        set_speaker_identifier(_speaker_id)

    yield

    if _speaker_id:
        _speaker_id.close()


def _health_details() -> dict:
    return {
        "model_loaded": _engine.is_loaded,
        "model_name": settings.model_size,
        "speaker_id_enabled": settings.speaker_id_enabled,
    }


app = FastAPI(title="dolores-stt", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-stt", "0.1.0", details_fn=_health_details))
app.include_router(stt_router)
