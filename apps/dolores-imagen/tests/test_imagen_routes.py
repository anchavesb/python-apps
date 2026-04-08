"""Tests for image generation API routes.

Uses FastAPI's TestClient (sync) with a mocked provider.
Heavy ML models are never instantiated.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from dolores_imagen import routes
from dolores_imagen.engine import ImageGenProvider
from dolores_imagen.routes import router, set_provider
from fastapi import FastAPI
from fastapi.testclient import TestClient

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class MockImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        return _FAKE_PNG


@pytest.fixture()
def mock_provider():
    return MockImageGenProvider()


@pytest.fixture()
def app(mock_provider):
    set_provider(mock_provider)
    _app = FastAPI()
    _app.include_router(router)
    yield _app
    routes._provider = None


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


class TestGenerateEndpoint:
    def test_returns_png_content_type(self, client):
        resp = client.post("/v1/generate", json={"prompt": "a snowy mountain"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_returns_image_bytes(self, client):
        resp = client.post("/v1/generate", json={"prompt": "a red fox"})
        assert resp.status_code == 200
        assert resp.content == _FAKE_PNG

    def test_empty_prompt_returns_422(self, client):
        resp = client.post("/v1/generate", json={"prompt": ""})
        assert resp.status_code == 422

    def test_missing_prompt_returns_422(self, client):
        resp = client.post("/v1/generate", json={"width": 512})
        assert resp.status_code == 422

    def test_custom_dimensions_accepted(self, client):
        resp = client.post("/v1/generate", json={"prompt": "test", "width": 256, "height": 256})
        assert resp.status_code == 200

    def test_provider_not_loaded_returns_503(self, client, mock_provider):
        mock_provider_not_loaded = MagicMock(spec=ImageGenProvider)
        mock_provider_not_loaded.is_loaded = False
        set_provider(mock_provider_not_loaded)
        resp = client.post("/v1/generate", json={"prompt": "test"})
        assert resp.status_code == 503
        set_provider(mock_provider)

    def test_provider_unset_returns_503(self, app):
        routes._provider = None
        with TestClient(app) as c:
            resp = c.post("/v1/generate", json={"prompt": "test"})
        assert resp.status_code == 503

    def test_generate_called_with_prompt(self, client, mock_provider):
        with patch.object(mock_provider, "generate", wraps=mock_provider.generate) as mock_gen:
            client.post("/v1/generate", json={"prompt": "a blue whale", "width": 512, "height": 512})
            mock_gen.assert_called_once_with("a blue whale", 512, 512)


class TestProvidersEndpoint:
    def test_returns_provider_name(self, client):
        resp = client.get("/v1/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "mock"

    def test_returns_loaded_status(self, client):
        resp = client.get("/v1/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["loaded"] is True

    def test_provider_not_loaded_returns_503(self, client, mock_provider):
        mock_provider_not_loaded = MagicMock(spec=ImageGenProvider)
        mock_provider_not_loaded.is_loaded = False
        set_provider(mock_provider_not_loaded)
        resp = client.get("/v1/providers")
        assert resp.status_code == 503
        set_provider(mock_provider)


class TestDevModeAuth:
    def test_unauthenticated_generate_succeeds_without_psk(self, client):
        """Dev mode: no DOLORES_SERVICE_PSK set means unauthenticated access is allowed."""
        env = {k: v for k, v in os.environ.items() if k != "DOLORES_SERVICE_PSK"}
        with patch.dict(os.environ, env, clear=True):
            resp = client.post("/v1/generate", json={"prompt": "test image"})
        assert resp.status_code == 200

    def test_unauthenticated_providers_succeeds_without_psk(self, client):
        env = {k: v for k, v in os.environ.items() if k != "DOLORES_SERVICE_PSK"}
        with patch.dict(os.environ, env, clear=True):
            resp = client.get("/v1/providers")
        assert resp.status_code == 200
