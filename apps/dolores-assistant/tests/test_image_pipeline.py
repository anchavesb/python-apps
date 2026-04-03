"""Tests for image analysis and generation pipeline in dolores-assistant."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dolores_assistant.routes import _process_and_respond, _process_image_message


async def _async_gen(*events):
    for event in events:
        yield event


class TestProcessImageMessage:
    """Tests for _process_image_message() WebSocket handler."""

    @pytest.fixture
    def mock_ws(self):
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.send_bytes = AsyncMock()
        return ws

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.synthesize = AsyncMock(return_value=None)
        return client

    def test_streams_token_events_as_response_text(self, mock_ws, mock_client):
        mock_client.analyze_image = MagicMock(
            return_value=_async_gen(
                {"type": "token", "content": "This "},
                {"type": "token", "content": "is a cat."},
                {"type": "done", "content": "This is a cat."},
            )
        )
        asyncio.run(
            _process_image_message(
                mock_ws,
                mock_client,
                "What is this?",
                "data:image/jpeg;base64,abc",
                "conv-1",
                "ollama",
                "default",
                "text",
            )
        )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        text_events = [c for c in calls if c.get("type") == "response.text"]
        contents = [e["content"] for e in text_events]
        assert "This " in contents
        assert "is a cat." in contents

    def test_sends_response_end(self, mock_ws, mock_client):
        mock_client.analyze_image = MagicMock(
            return_value=_async_gen(
                {"type": "done", "content": "Looks good."},
            )
        )
        asyncio.run(
            _process_image_message(
                mock_ws,
                mock_client,
                "Describe this.",
                "data:image/png;base64,xyz",
                None,
                "ollama",
                "default",
                "text",
            )
        )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        end_events = [c for c in calls if c.get("type") == "response.end"]
        assert len(end_events) == 1

    def test_brain_error_sends_error_event_and_stops(self, mock_ws, mock_client):
        mock_client.analyze_image = MagicMock(
            return_value=_async_gen(
                {"type": "error", "error": "model unavailable"},
            )
        )
        asyncio.run(
            _process_image_message(
                mock_ws,
                mock_client,
                "Analyze this.",
                "data:image/jpeg;base64,abc",
                None,
                "ollama",
                "default",
                "text",
            )
        )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        error_events = [c for c in calls if c.get("type") == "error"]
        assert len(error_events) == 1
        assert error_events[0]["code"] == "brain_error"
        end_events = [c for c in calls if c.get("type") == "response.end"]
        assert len(end_events) == 0


class TestImageGenerationPipeline:
    """Tests for generate_image path in _process_and_respond()."""

    @pytest.fixture
    def mock_ws(self):
        ws = MagicMock()
        ws.send_json = AsyncMock()
        ws.send_bytes = AsyncMock()
        return ws

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    def test_sends_generating_text_before_request(self, mock_ws, mock_client):
        mock_client.generate_image = AsyncMock(return_value=b"\x89PNG\r\n" + b"\x00" * 50)
        with patch(
            "dolores_assistant.routes.classify_intent", return_value=("generate_image", {"generate_image"}, 0.9)
        ):
            asyncio.run(
                _process_and_respond(
                    mock_ws,
                    mock_client,
                    "generate a red fox in snow",
                    "conv-1",
                    "ollama",
                    "default",
                    "text",
                )
            )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        first_text = next(c for c in calls if c.get("type") == "response.text")
        assert first_text["content"] == "Generating your image..."

    def test_sends_response_image_event_with_correct_data(self, mock_ws, mock_client):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_client.generate_image = AsyncMock(return_value=png_bytes)
        with patch(
            "dolores_assistant.routes.classify_intent", return_value=("generate_image", {"generate_image"}, 0.9)
        ):
            asyncio.run(
                _process_and_respond(
                    mock_ws,
                    mock_client,
                    "generate a red fox in snow",
                    "conv-1",
                    "ollama",
                    "default",
                    "text",
                )
            )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        image_events = [c for c in calls if c.get("type") == "response.image"]
        assert len(image_events) == 1
        expected_b64 = base64.b64encode(png_bytes).decode()
        assert image_events[0]["image_data"] == f"data:image/png;base64,{expected_b64}"
        assert image_events[0]["prompt"] == "generate a red fox in snow"

    def test_sends_descriptive_error_when_generate_image_returns_none(self, mock_ws, mock_client):
        mock_client.generate_image = AsyncMock(return_value=None)
        with patch(
            "dolores_assistant.routes.classify_intent", return_value=("generate_image", {"generate_image"}, 0.9)
        ):
            asyncio.run(
                _process_and_respond(
                    mock_ws,
                    mock_client,
                    "make a picture of a cat",
                    "conv-1",
                    "ollama",
                    "default",
                    "text",
                )
            )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        text_events = [c for c in calls if c.get("type") == "response.text"]
        assert len(text_events) >= 2
        assert text_events[-1]["content"]
        end_events = [c for c in calls if c.get("type") == "response.end"]
        assert len(end_events) == 1

    def test_generate_image_path_sends_response_end(self, mock_ws, mock_client):
        mock_client.generate_image = AsyncMock(return_value=b"\x89PNG" + b"\x00" * 20)
        with patch(
            "dolores_assistant.routes.classify_intent", return_value=("generate_image", {"generate_image"}, 0.9)
        ):
            asyncio.run(
                _process_and_respond(
                    mock_ws,
                    mock_client,
                    "draw a sunset",
                    None,
                    "ollama",
                    "default",
                    "text",
                )
            )
        calls = [c.args[0] for c in mock_ws.send_json.call_args_list]
        end_events = [c for c in calls if c.get("type") == "response.end"]
        assert len(end_events) == 1


class TestGenerateImageIntentExamples:
    """Validate generate_image intent configuration."""

    def test_generate_image_intent_exists(self):
        from dolores_assistant.intent import INTENT_EXAMPLES

        assert "generate_image" in INTENT_EXAMPLES

    def test_generate_image_has_sufficient_examples(self):
        from dolores_assistant.intent import INTENT_EXAMPLES

        _, examples = INTENT_EXAMPLES["generate_image"]
        assert len(examples) >= 10

    def test_generate_image_tool_filter_is_nonempty_set(self):
        from dolores_assistant.intent import INTENT_EXAMPLES

        tool_filter, _ = INTENT_EXAMPLES["generate_image"]
        assert isinstance(tool_filter, set)
        assert len(tool_filter) > 0
