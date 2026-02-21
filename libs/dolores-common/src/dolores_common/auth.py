"""Authentication middleware for Dolores services.

- PSK (pre-shared key) for inter-service authentication
- API key for client authentication
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket


def _get_psk() -> str | None:
    """Get the service PSK from environment."""
    return os.environ.get("DOLORES_SERVICE_PSK")


def _get_api_key() -> str | None:
    """Get the client API key from environment."""
    return os.environ.get("DOLORES_API_KEY")


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract token from Authorization: Bearer <token> header."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


async def require_service_psk(request: Request) -> None:
    """FastAPI dependency that validates the inter-service PSK.

    Skip validation if DOLORES_SERVICE_PSK is not set (dev mode).
    """
    psk = _get_psk()
    if not psk:
        return  # No PSK configured, skip auth (dev mode)

    token = _extract_bearer_token(request.headers.get("authorization"))
    if token != psk:
        raise HTTPException(status_code=401, detail="Invalid service PSK")


async def require_api_key(request: Request) -> None:
    """FastAPI dependency that validates the client API key.

    Skip validation if DOLORES_API_KEY is not set (dev mode).
    """
    api_key = _get_api_key()
    if not api_key:
        return  # No API key configured, skip auth (dev mode)

    token = _extract_bearer_token(request.headers.get("authorization"))
    if token != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def validate_ws_token(websocket: WebSocket) -> None:
    """Validate API key for WebSocket connections.

    Accepts token as query parameter (?token=...) or in the first message.
    Skip validation if DOLORES_API_KEY is not set (dev mode).
    """
    api_key = _get_api_key()
    if not api_key:
        return  # No API key configured, skip auth (dev mode)

    token = websocket.query_params.get("token")
    if token != api_key:
        await websocket.close(code=4001, reason="Invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API key")


ServicePSK = Annotated[None, Depends(require_service_psk)]
ClientAPIKey = Annotated[None, Depends(require_api_key)]
