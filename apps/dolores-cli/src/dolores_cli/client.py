"""WebSocket client for connecting to the dolores-assistant service."""

from __future__ import annotations

import json
from typing import AsyncGenerator

import websockets

from .config import settings


class DoloresClient:
    """WebSocket client to the assistant orchestrator."""

    def __init__(
        self,
        server_url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._server_url = server_url or settings.server_url
        self._api_key = api_key or settings.api_key
        self._provider = provider or settings.provider
        self._ws = None
        self._conversation_id: str | None = None

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    async def connect(self, conversation_id: str | None = None) -> None:
        """Connect to the assistant and start a session."""
        ws_url = f"{self._server_url}/v1/conversation"
        if self._api_key:
            ws_url += f"?token={self._api_key}"

        self._ws = await websockets.connect(ws_url)

        # Send session.start
        session_msg = {
            "type": "session.start",
            "mode": "text",
            "token": self._api_key,
        }
        if self._provider:
            session_msg["provider"] = self._provider
        if conversation_id:
            session_msg["conversation_id"] = conversation_id

        await self._ws.send(json.dumps(session_msg))

        # Wait for session.created
        raw = await self._ws.recv()
        resp = json.loads(raw)
        if resp.get("type") == "session.created":
            self._conversation_id = resp.get("conversation_id")

    async def send_text(self, text: str) -> AsyncGenerator[dict, None]:
        """Send a text message and yield response events."""
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        await self._ws.send(json.dumps({"type": "text.send", "text": text}))

        while True:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                # Audio data — skip in text mode
                continue

            event = json.loads(raw)
            yield event

            if event.get("type") in ("response.end", "error"):
                break

    async def close(self) -> None:
        """End the session and close the connection."""
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "session.end"}))
            except Exception:
                pass
            await self._ws.close()
            self._ws = None
