"""JWT bearer token authentication for mobile/API clients.

Validates access tokens issued by Authentik (OIDC) so that native apps
can authenticate without browser session cookies.

Supports multiple OIDC providers (e.g. web + mobile) via OIDC_JWT_ISSUERS.
"""
from __future__ import annotations

import logging
from typing import Optional

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# List of trusted (jwks_client, audience, issuer) tuples
_trusted_providers: list[tuple[PyJWKClient, str, str]] = []


def init_jwt_auth(app) -> None:
    """Initialize JWT validation from app config.

    Reads the primary OIDC_ISSUER/OIDC_CLIENT_ID, plus any additional
    issuers from OIDC_JWT_ISSUERS (comma-separated "issuer|client_id" pairs).
    """
    global _trusted_providers
    _trusted_providers = []

    if not app.config.get("OIDC_ENABLED"):
        logger.info("JWT auth disabled (OIDC not enabled)")
        return

    # Primary provider (the web OIDC provider)
    primary_issuer = app.config.get("OIDC_ISSUER", "").strip()
    primary_client_id = app.config.get("OIDC_CLIENT_ID", "")

    if primary_issuer and primary_client_id:
        _add_provider(primary_issuer, primary_client_id)

    # Additional providers (e.g. mobile app)
    # Format: "issuer_url|client_id,issuer_url|client_id,..."
    extra = app.config.get("OIDC_JWT_ISSUERS", "")
    if extra:
        for entry in extra.split(","):
            entry = entry.strip()
            if "|" in entry:
                issuer, client_id = entry.split("|", 1)
                _add_provider(issuer.strip(), client_id.strip())

    if _trusted_providers:
        logger.info("JWT auth enabled — %d trusted provider(s)", len(_trusted_providers))
    else:
        logger.warning("JWT auth disabled: no valid providers configured")


def _add_provider(issuer: str, client_id: str) -> None:
    """Register a trusted OIDC provider.

    The issuer URL is stored as-is (including any trailing slash) so that
    it matches the ``iss`` claim in JWTs issued by the provider.
    Only the JWKS URI strips a trailing slash to avoid double-slashes.
    """
    jwks_uri = f"{issuer.rstrip('/')}/jwks/"
    logger.info("JWT: trusting issuer %s (audience: %s, JWKS: %s)", issuer, client_id, jwks_uri)
    client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)
    _trusted_providers.append((client, client_id, issuer))


def validate_bearer_token(token: str) -> Optional[dict]:
    """Validate a JWT bearer token and return user claims.

    Tries each trusted provider until one succeeds.
    Returns a dict with keys: sub, email, name (matching session format)
    or None if validation fails against all providers.
    """
    if not _trusted_providers:
        return None

    for jwks_client, audience, issuer in _trusted_providers:
        result = _try_validate(token, jwks_client, audience, issuer)
        if result is not None:
            return result

    logger.debug("JWT rejected by all %d providers", len(_trusted_providers))
    return None


def _try_validate(token: str, jwks_client: PyJWKClient, audience: str, issuer: str) -> Optional[dict]:
    """Try to validate a token against a single provider."""
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
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
        logger.debug("JWT expired (issuer: %s)", issuer)
        return None
    except jwt.InvalidAudienceError:
        # Expected when trying wrong provider — don't log as warning
        return None
    except jwt.InvalidIssuerError:
        return None
    except jwt.PyJWKClientError as e:
        logger.warning("JWKS key fetch failed for %s: %s", issuer, e)
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT validation failed (%s): %s", issuer, e)
        return None
    except Exception as e:
        logger.error("Unexpected JWT error (%s): %s", issuer, e)
        return None
