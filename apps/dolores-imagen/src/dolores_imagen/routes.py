"""Image generation API routes: POST /v1/generate, GET /v1/providers."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from dolores_common.auth import ServicePSK
from dolores_common.logging import get_logger

from .engine import ImageGenProvider
from .schemas import GenerateRequest, ProviderInfo

log = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["imagen"])

_provider: ImageGenProvider | None = None
_semaphore = asyncio.Semaphore(1)


def get_provider() -> ImageGenProvider:
    if _provider is None or not _provider.is_loaded:
        raise HTTPException(status_code=503, detail="Image generation model not loaded yet")
    return _provider


def set_provider(provider: ImageGenProvider) -> None:
    global _provider
    _provider = provider


@router.post("/generate")
async def generate_image(
    req: GenerateRequest,
    _auth: ServicePSK = None,
    provider: ImageGenProvider = Depends(get_provider),
) -> Response:
    """Generate image from text prompt. Returns PNG binary."""
    log.info("generate_request", prompt_length=len(req.prompt), width=req.width, height=req.height)

    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=60.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="GPU busy — try again shortly")
    try:
        image_bytes = await asyncio.to_thread(provider.generate, req.prompt, req.width, req.height)
    finally:
        _semaphore.release()

    return Response(content=image_bytes, media_type="image/png")


@router.get("/providers", response_model=ProviderInfo)
async def get_providers(
    _auth: ServicePSK = None,
    provider: ImageGenProvider = Depends(get_provider),
) -> ProviderInfo:
    """Return active provider name and load status."""
    return ProviderInfo(provider=provider.name, loaded=provider.is_loaded)
