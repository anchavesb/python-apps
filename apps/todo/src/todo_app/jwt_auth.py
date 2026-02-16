"""JWT bearer token authentication for mobile/API clients.

Validates access tokens issued by Authentik (OIDC) so that native apps
can authenticate without browser session cookies.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Module-level JWKS client — initialized once via init_jwt_auth()
_jwks_client: Optional[PyJWKClient] = None
_jwt_audience: Optional[str] = None
_jwt_issuer: Optional[str] = None


def init_jwt_auth(app) -> None:
    """Initialize JWT validation from app config.

    Requires OIDC_ENABLED=1 and valid OIDC_ISSUER / OIDC_CLIENT_ID.
    """
    global _jwks_client, _jwt_audience, _jwt_issuer

    if not app.config.get("OIDC_ENABLED"):
        logger.info("JWT auth disabled (OIDC not enabled)")
        return

    issuer = app.config["OIDC_ISSUER"].rstrip("/")
    client_id = app.config["OIDC_CLIENT_ID"]

    if not issuer or not client_id:
        logger.warning("JWT auth disabled: OIDC_ISSUER or OIDC_CLIENT_ID not set")
        return

    # Authentik publishes JWKS at the issuer's jwks endpoint.
    # We derive it from the OpenID Connect discovery document.
    jwks_uri = f"{issuer}/jwks/"
    logger.info("JWT auth enabled — JWKS URI: %s", jwks_uri)

    _jwks_client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
    _jwt_audience = client_id
    _jwt_issuer = issuer


def validate_bearer_token(token: str) -> Optional[dict]:
    """Validate a JWT bearer token and return user claims.

    Returns a dict with keys: sub, email, name (matching session format)
    or None if validation fails.
    """
    if not _jwks_client:
        return None

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=_jwt_audience,
            issuer=_jwt_issuer,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        # Extract user info from token claims (Authentik standard claims)
        user_info = {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name") or payload.get("preferred_username"),
            "groups": payload.get("groups", []),
        }

        if not user_info["sub"]:
            logger.warning("JWT valid but missing 'sub' claim")
            return None

        return user_info

    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except jwt.InvalidAudienceError:
        logger.debug("JWT audience mismatch")
        return None
    except jwt.InvalidIssuerError:
        logger.debug("JWT issuer mismatch")
        return None
    except jwt.PyJWKClientError as e:
        logger.warning("JWKS key fetch failed: %s", e)
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT validation failed: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected JWT error: %s", e)
        return None
