"""Tests for ServiceClient.synthesize() emotion plumbing in pipeline.py."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dolores_assistant.pipeline import ServiceClient


class TestServiceClientSynthesize:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = ServiceClient()
        self.client._client = AsyncMock()

    def _make_response(self, content: bytes = b"RIFF\x00\x00\x00\x00WAVE") -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.raise_for_status = MagicMock()
        return resp

    def test_synthesize_includes_emotion_in_payload(self):
        """POST body always contains emotion key, serialized as null when not provided."""
        self.client._client.post = AsyncMock(return_value=self._make_response())

        asyncio.run(self.client.synthesize("Hello world"))

        call_kwargs = self.client._client.post.call_args.kwargs
        body = call_kwargs["json"]
        assert "emotion" in body
        assert body["emotion"] is None

    def test_synthesize_forwards_emotion_value(self):
        """When emotion='happy' is passed, the POST body contains emotion='happy'."""
        self.client._client.post = AsyncMock(return_value=self._make_response())

        asyncio.run(self.client.synthesize("Hello world", emotion="happy"))

        call_kwargs = self.client._client.post.call_args.kwargs
        body = call_kwargs["json"]
        assert body["emotion"] == "happy"


@pytest.mark.anyio
async def test_transcribe_stream_yields_partials_and_final():
    """ServiceClient.transcribe_stream should yield messages from STT WebSocket."""
    client = ServiceClient()

    # Mock websockets.connect
    with patch("websockets.connect") as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_ws

        # Generator for websocket messages
        mock_ws.__aiter__.return_value = [
            json.dumps({"type": "partial", "text": "Hello"}),
            json.dumps({"type": "partial", "text": "Hello world"}),
            json.dumps({"type": "final", "text": "Hello world."}),
        ]

        results = []
        async for chunk in client.transcribe_stream(b"audio-data"):
            results.append(chunk)

        assert len(results) == 3
        assert results[0]["text"] == "Hello"
        assert results[1]["text"] == "Hello world"
        assert results[2]["type"] == "final"

        # Verify audio and end signal were sent
        mock_ws.send.assert_any_call(b"audio-data")
        last_send = mock_ws.send.call_args_list[-1].args[0]
        assert json.loads(last_send)["type"] == "audio.end"
