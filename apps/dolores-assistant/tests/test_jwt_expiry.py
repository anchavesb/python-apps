"""Tests for JWT expiry checking."""

import base64
import json
import time

from dolores_assistant.pipeline import _is_jwt_expired


def _make_jwt(payload: dict) -> str:
    """Create a fake JWT with the given payload (no signature verification)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesignature"


class TestIsJwtExpired:
    def test_expired_token(self):
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) - 3600})
        assert _is_jwt_expired(token) is True

    def test_valid_token(self):
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) + 3600})
        assert _is_jwt_expired(token) is False

    def test_no_exp_claim(self):
        """Token without exp claim is treated as not expired."""
        token = _make_jwt({"sub": "user1"})
        assert _is_jwt_expired(token) is False

    def test_just_expired(self):
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) - 1})
        assert _is_jwt_expired(token) is True

    def test_expires_soon_but_valid(self):
        token = _make_jwt({"sub": "user1", "exp": int(time.time()) + 10})
        assert _is_jwt_expired(token) is False

    def test_invalid_token_returns_false(self):
        """Malformed tokens should not crash, just return False."""
        assert _is_jwt_expired("not.a.jwt") is False
        assert _is_jwt_expired("") is False
        assert _is_jwt_expired("onlyone") is False

    def test_corrupted_payload_returns_false(self):
        assert _is_jwt_expired("header.!!!notbase64!!!.sig") is False
