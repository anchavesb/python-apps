"""Common FastAPI middleware for Dolores services."""

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware


def add_common_middleware(app: FastAPI, allowed_origins: list[str] | None = None) -> None:
    """Add CORS and request ID middleware to a FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        """Generate or propagate a request ID and bind it to structlog context."""
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response
