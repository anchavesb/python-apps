"""Tests for multimodal (image + text) chat support in dolores-brain."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dolores_brain.provider_config import PROVIDERS, resolve_model
from dolores_brain.routes import _build_user_content, router, set_store


class TestBuildUserContent:
    def test_text_only_returns_string(self):
        result = _build_user_content("Hello", None)
        assert result == "Hello"

    def test_with_image_returns_content_blocks(self):
        image_url = "data:image/jpeg;base64,abc123"
        result = _build_user_content("Describe this", image_url)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "Describe this"}
        assert result[1] == {"type": "image_url", "image_url": {"url": image_url}}

    def test_empty_image_data_returns_string(self):
        result = _build_user_content("Hello", "")
        assert result == "Hello"

    def test_message_text_preserved_in_content_block(self):
        result = _build_user_content("What is in this image?", "data:image/png;base64,xyz")
        assert isinstance(result, list)
        assert result[0]["text"] == "What is in this image?"


class TestResolveModelVisionOverride:
    def setup_method(self):
        PROVIDERS["ollama"] = {
            "name": "ollama",
            "prefix": "ollama/",
            "models": ["llama3.2"],
            "default_model": "llama3.2",
        }
        PROVIDERS["anthropic"] = {
            "name": "anthropic",
            "prefix": "",
            "models": ["claude-sonnet-4-20250514"],
            "default_model": "claude-sonnet-4-20250514",
        }

    def teardown_method(self):
        PROVIDERS.pop("ollama", None)
        PROVIDERS.pop("anthropic", None)

    def test_vision_provider_overrides_request_provider(self):
        model_str = resolve_model("ollama", None, vision_provider="anthropic")
        assert model_str == "claude-sonnet-4-20250514"

    def test_empty_vision_provider_uses_request_provider(self):
        model_str = resolve_model("ollama", None, vision_provider="")
        assert model_str == "ollama/llama3.2"

    def test_none_vision_provider_uses_request_provider(self):
        model_str = resolve_model("ollama", None, vision_provider=None)
        assert model_str == "ollama/llama3.2"

    def test_vision_provider_with_explicit_model_ignored_in_model_selection(self):
        model_str = resolve_model("ollama", None, vision_provider="anthropic")
        assert "ollama" not in model_str


@pytest.fixture()
def _test_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def mock_store():
    store = MagicMock()
    store.exists = AsyncMock(return_value=False)
    store.create = AsyncMock(return_value="test-conv-id")
    store.get_history = AsyncMock(return_value=[])
    store.append = AsyncMock()
    return store


@pytest.fixture()
def _setup_providers():
    PROVIDERS["ollama"] = {
        "name": "ollama",
        "prefix": "ollama/",
        "models": ["llama3.2"],
        "default_model": "llama3.2",
    }
    yield
    PROVIDERS.pop("ollama", None)


@pytest.fixture()
def client(_test_app, mock_store, _setup_providers):
    set_store(mock_store)
    return TestClient(_test_app)


def _make_mock_response(content: str = "OK"):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_response.choices[0].message.tool_calls = None
    mock_response.usage = None
    return mock_response


class TestChatWithImageData:
    def test_chat_multimodal_returns_200(self, client):
        with patch(
            "dolores_brain.routes.litellm.acompletion", new=AsyncMock(return_value=_make_mock_response("Analysis."))
        ):
            resp = client.post(
                "/v1/chat",
                json={"message": "What is this?", "image_data": "data:image/jpeg;base64,abc123"},
            )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Analysis."

    def test_chat_multimodal_stores_json_encoded_content(self, client, mock_store):
        with patch("dolores_brain.routes.litellm.acompletion", new=AsyncMock(return_value=_make_mock_response())):
            client.post(
                "/v1/chat",
                json={"message": "What is this?", "image_data": "data:image/jpeg;base64,abc123"},
            )

        first_append_call = mock_store.append.call_args_list[0]
        stored_content = first_append_call.args[2]
        parsed = json.loads(stored_content)
        assert isinstance(parsed, list)
        assert parsed[0] == {"type": "text", "text": "What is this?"}
        assert parsed[1]["type"] == "image_url"
        assert parsed[1]["image_url"]["url"] == "data:image/jpeg;base64,abc123"

    def test_chat_without_image_stores_plain_string(self, client, mock_store):
        with patch("dolores_brain.routes.litellm.acompletion", new=AsyncMock(return_value=_make_mock_response())):
            client.post("/v1/chat", json={"message": "Hello"})

        first_append_call = mock_store.append.call_args_list[0]
        stored_content = first_append_call.args[2]
        assert stored_content == "Hello"

    def test_chat_multimodal_sends_content_blocks_to_llm(self, client):
        captured: dict = {}

        async def capturing_acompletion(**kwargs):
            captured["messages"] = kwargs["messages"]
            return _make_mock_response()

        with patch("dolores_brain.routes.litellm.acompletion", side_effect=capturing_acompletion):
            client.post(
                "/v1/chat",
                json={"message": "Describe this", "image_data": "data:image/png;base64,xyz"},
            )

        user_msg = next(m for m in captured["messages"] if m["role"] == "user")
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0]["type"] == "text"
        assert user_msg["content"][1]["type"] == "image_url"

    def test_chat_uses_vision_provider_when_image_present(self, mock_store, _setup_providers):
        PROVIDERS["anthropic"] = {
            "name": "anthropic",
            "prefix": "",
            "models": ["claude-sonnet-4-20250514"],
            "default_model": "claude-sonnet-4-20250514",
        }
        captured: dict = {}

        async def capturing_acompletion(**kwargs):
            captured["model"] = kwargs["model"]
            return _make_mock_response()

        app = FastAPI()
        app.include_router(router)
        set_store(mock_store)

        with patch("dolores_brain.routes.settings") as mock_settings:
            mock_settings.vision_provider = "anthropic"
            mock_settings.default_provider = "ollama"
            mock_settings.max_history_messages = 20
            with patch("dolores_brain.routes.litellm.acompletion", side_effect=capturing_acompletion):
                with TestClient(app) as c:
                    c.post(
                        "/v1/chat",
                        json={"message": "Describe this image", "image_data": "data:image/jpeg;base64,abc"},
                    )

        assert captured.get("model") == "claude-sonnet-4-20250514"
        PROVIDERS.pop("anthropic", None)
