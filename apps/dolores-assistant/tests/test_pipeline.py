"""Tests for ServiceClient.synthesize() emotion plumbing in pipeline.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

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
