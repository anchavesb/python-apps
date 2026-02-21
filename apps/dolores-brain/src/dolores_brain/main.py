"""FastAPI application for dolores-brain."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .conversation import ConversationStore
from .provider_config import PROVIDERS, setup_providers
from .routes import router as brain_router, set_store

_store = ConversationStore(settings.db_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("dolores-brain", settings.log_level, json_output=settings.log_format == "json")

    # Ensure data directory exists
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

    setup_providers()
    await _store.init()
    set_store(_store)
    yield
    await _store.close()


def _health_details() -> dict:
    return {"providers": {name: True for name in PROVIDERS}}


app = FastAPI(title="dolores-brain", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-brain", "0.1.0", details_fn=_health_details))
app.include_router(brain_router)
