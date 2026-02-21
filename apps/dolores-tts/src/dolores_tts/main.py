"""FastAPI application for dolores-tts."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .routes import router as tts_router, set_engine, set_voice_store
from .voice_profiles import VoiceProfileStore

_engine = None
_voice_store = VoiceProfileStore(settings.voices_dir, settings.db_path)


def _create_engine():
    """Create the appropriate TTS engine based on config."""
    if settings.engine == "coqui_xtts":
        from .engines.coqui_xtts import CoquiXTTSEngine
        return CoquiXTTSEngine(device=settings.device, voices_dir=settings.voices_dir)
    elif settings.engine == "piper":
        from .engines.piper import PiperEngine
        return PiperEngine()
    else:
        raise ValueError(f"Unknown TTS engine: {settings.engine}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    setup_logging("dolores-tts", settings.log_level, json_output=settings.log_format == "json")

    # Ensure data directories exist
    os.makedirs(settings.voices_dir, exist_ok=True)
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

    _engine = _create_engine()
    _engine.load()
    set_engine(_engine)

    await _voice_store.init()
    set_voice_store(_voice_store)

    yield
    await _voice_store.close()


def _health_details() -> dict:
    engines = {}
    if _engine:
        engines[_engine.name] = _engine.is_loaded
    return {"engines": engines}


app = FastAPI(title="dolores-tts", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-tts", "0.1.0", details_fn=_health_details))
app.include_router(tts_router)
