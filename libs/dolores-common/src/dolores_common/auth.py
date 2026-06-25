from __future__ import annotations

import logging
import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

_jwks_clients: dict[str, PyJWKClient] = {}



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
    """FastAPI dependency that validates client auth.

    Validates OIDC JWT if OIDC is enabled, otherwise falls back to static client API key.
    """
    if os.environ.get("OIDC_ENABLED", "0") == "1":
        await require_oidc_user(request)
        return

    api_key = _get_api_key()
    if not api_key:
        return  # No API key configured, skip auth (dev mode)

    token = _extract_bearer_token(request.headers.get("authorization"))
    if token != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def validate_ws_token(websocket: WebSocket) -> None:
    """Validate token for WebSocket connections.

    Validates OIDC JWT if OIDC is enabled, otherwise falls back to static client API key.
    """
    token = websocket.query_params.get("token")
    if os.environ.get("OIDC_ENABLED", "0") == "1":
        if not token:
            await websocket.close(code=4001, reason="Missing OIDC token")
            raise HTTPException(status_code=401, detail="Missing OIDC token")
        payload = validate_oidc_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired OIDC token")
            raise HTTPException(status_code=401, detail="Invalid OIDC token")
        return

    api_key = _get_api_key()
    if not api_key:
        return  # No API key configured, skip auth (dev mode)

    if token != api_key:
        await websocket.close(code=4001, reason="Invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API key")


ServicePSK = Annotated[None, Depends(require_service_psk)]
ClientAPIKey = Annotated[None, Depends(require_api_key)]


def _get_jwks_client(issuer: str) -> PyJWKClient:
    """Get or create cached PyJWKClient for issuer."""
    if issuer not in _jwks_clients:
        jwks_uri = f"{issuer.rstrip('/')}/jwks/"
        _jwks_clients[issuer] = PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
    return _jwks_clients[issuer]


def validate_oidc_token(token: str) -> dict | None:
    """Validate token against configured Authentik/OIDC issuer.

    Returns token payload (claims dict) if valid, or None if validation fails or OIDC is disabled.
    """
    if os.environ.get("OIDC_ENABLED", "0") != "1":
        # Dev fallback: return default user payload when OIDC is disabled
        return {"sub": "anonymous", "email": "anonymous@local", "name": "Anonymous"}

    issuer = os.environ.get("OIDC_ISSUER", "")
    audience = os.environ.get("OIDC_CLIENT_ID", "")
    if not issuer or not audience:
        logger.warning("OIDC_ENABLED is 1 but OIDC_ISSUER or OIDC_CLIENT_ID is not configured")
        return None

    try:
        jwks_client = _get_jwks_client(issuer)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )
        return payload
    except Exception as e:
        logger.debug("OIDC JWT validation failed", error=str(e))
        return None


async def require_oidc_user(request: Request) -> dict:
    """FastAPI dependency that validates OIDC token in Authorization or X-User-Token header."""
    if os.environ.get("OIDC_ENABLED", "0") != "1":
        return {"sub": "anonymous", "email": "anonymous@local", "name": "Anonymous"}

    token = _extract_bearer_token(request.headers.get("authorization"))
    if not token:
        token = request.headers.get("x-user-token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing OIDC token")

    payload = validate_oidc_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired OIDC token")

    return payload


OIDCUser = Annotated[dict, Depends(require_oidc_user)]


def extract_user_id(token: str | None) -> str:
    """Validate token and extract user claim (sub or email) if OIDC is enabled.

    Falls back to unverified payload parsing in dev mode (OIDC_ENABLED=0).
    """
    if not token:
        return "anonymous"

    if os.environ.get("OIDC_ENABLED", "0") == "1":
        payload = validate_oidc_token(token)
        if not payload:
            return "anonymous"
        return payload.get("sub") or payload.get("email") or "anonymous"

    # Dev fallback: decode without verification if OIDC is disabled
    try:
        import base64
        import json
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("sub") or data.get("email") or "anonymous"
    except Exception:
        return "anonymous"


