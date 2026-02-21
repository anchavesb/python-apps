"""Standard health check endpoint factory for FastAPI services."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter


def create_health_router(
    service_name: str,
    version: str,
    details_fn: Callable[[], dict | Coroutine[Any, Any, dict]] | None = None,
) -> APIRouter:
    """Create a health check router with uptime tracking.

    Args:
        service_name: Name of the service.
        version: Version string.
        details_fn: Optional callable returning extra details. Can be sync or async.
    """
    router = APIRouter()
    start_time = time.time()

    @router.get("/health")
    async def health() -> dict:
        result = {
            "status": "ok",
            "service": service_name,
            "version": version,
            "uptime_seconds": round(time.time() - start_time, 1),
        }
        if details_fn is not None:
            details = details_fn()
            if asyncio.iscoroutine(details):
                details = await details
            result.update(details)
        return result

    return router
