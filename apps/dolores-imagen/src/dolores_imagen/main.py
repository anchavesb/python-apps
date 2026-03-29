"""FastAPI application for dolores-imagen."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from dolores_common.health import create_health_router
from dolores_common.logging import get_logger, setup_logging
from dolores_common.middleware import add_common_middleware

from .config import settings
from .routes import router as imagen_router
from .routes import set_provider

log = get_logger(__name__)

_provider = None


def _create_provider():
    """Create the appropriate image generation provider based on config."""
    if settings.provider == "stable_diffusion":
        from .engines.stable_diffusion import StableDiffusionProvider

        return StableDiffusionProvider(model_id=settings.sd_model_id)
    else:
        from .engines.flux import FLUXProvider

        return FLUXProvider(model_id=settings.flux_model_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _provider
    setup_logging("dolores-imagen", settings.log_level, json_output=settings.log_format == "json")

    _provider = _create_provider()
    try:
        _provider.load()
    except Exception:
        log.exception("provider_load_failed", provider=_provider.name)
        raise
    set_provider(_provider)

    yield


def _health_details() -> dict:
    providers = {}
    if _provider:
        providers[_provider.name] = _provider.is_loaded
    return {"providers": providers}


app = FastAPI(title="dolores-imagen", lifespan=lifespan)

add_common_middleware(app)
app.include_router(create_health_router("dolores-imagen", "0.1.0", details_fn=_health_details))
app.include_router(imagen_router)
