"""FastAPI application for dolores-assistant orchestrator."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .pipeline import ServiceClient
from .routes import router as assistant_router, set_service_client

_service_client = ServiceClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("dolores-assistant", settings.log_level, json_output=settings.log_format == "json")
    await _service_client.start()
    set_service_client(_service_client)
    yield
    await _service_client.close()


async def _health_details() -> dict:
    services = await _service_client.check_all_services()
    return {"services": services}


app = FastAPI(title="dolores-assistant", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-assistant", "0.1.0", details_fn=_health_details))
app.include_router(assistant_router)
