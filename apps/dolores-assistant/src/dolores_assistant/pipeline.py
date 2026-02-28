"""Pipeline orchestration: STT -> Brain -> TTS with graceful degradation.

Manages HTTP clients to downstream services, GPU concurrency control,
sentence-level TTS streaming, and the tool-calling agent loop.
"""

from __future__ import annotations

import asyncio
import json
import re
import os
from typing import AsyncGenerator

import httpx

from dolores_common.logging import get_logger

from .config import settings
from .tools.registry import get_tool_by_name, get_tool_definitions

log = get_logger(__name__)

# GPU concurrency: only one request at a time per GPU service
_stt_semaphore = asyncio.Semaphore(1)
_tts_semaphore = asyncio.Semaphore(1)

# Sentence boundary regex for TTS chunking
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


def _auth_headers() -> dict[str, str]:
    """Build PSK auth headers for inter-service calls."""
    psk = os.environ.get("DOLORES_SERVICE_PSK", "")
    if psk:
        return {"Authorization": f"Bearer {psk}"}
    return {}


class ServiceClient:
    """HTTP client for downstream services."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(headers=_auth_headers(), timeout=60)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("ServiceClient not started")
        return self._client

    # --- STT ---

    async def transcribe(self, audio_data: bytes, content_type: str = "audio/webm") -> dict | None:
        """Send audio to STT service. Returns transcription dict or None on failure."""
        async with _stt_semaphore:
            try:
                resp = await self.client.post(
                    f"{settings.stt_url}/v1/transcribe",
                    files={"file": ("audio.webm", audio_data, content_type)},
                    timeout=settings.stt_timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                log.error("stt_call_failed", error=str(e))
                return None

    # --- Brain ---

    async def chat(
        self,
        message: str,
        conversation_id: str | None = None,
        provider: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict | None:
        """Send a chat message to Brain. Returns response dict or None."""
        try:
            body = {
                "message": message,
                "conversation_id": conversation_id,
                "provider": provider or settings.default_provider,
            }
            if tools:
                body["tools"] = tools

            resp = await self.client.post(
                f"{settings.brain_url}/v1/chat",
                json=body,
                timeout=settings.brain_timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("brain_call_failed", error=str(e))
            return None

    async def chat_stream(
        self,
        message: str,
        conversation_id: str | None = None,
        provider: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream chat tokens from Brain via SSE. Yields event dicts."""
        try:
            body = {
                "message": message,
                "conversation_id": conversation_id,
                "provider": provider or settings.default_provider,
            }
            if tools:
                body["tools"] = tools

            async with self.client.stream(
                "POST",
                f"{settings.brain_url}/v1/chat/stream",
                json=body,
                timeout=settings.brain_timeout,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            yield json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            log.error("brain_stream_failed", error=str(e))
            yield {"type": "error", "error": str(e)}

    # --- TTS ---

    async def synthesize(
        self, text: str, voice_id: str = "default"
    ) -> bytes | None:
        """Send text to TTS service. Returns WAV bytes or None on failure."""
        async with _tts_semaphore:
            try:
                resp = await self.client.post(
                    f"{settings.tts_url}/v1/synthesize",
                    json={"text": text, "voice_id": voice_id},
                    timeout=settings.tts_timeout,
                )
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                log.error("tts_call_failed", error=str(e))
                return None

    # --- Health checks ---

    async def check_service(self, name: str, url: str) -> str:
        """Check health of a downstream service. Returns 'healthy' or 'unhealthy'."""
        try:
            resp = await self.client.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                return "healthy"
        except Exception:
            pass
        return "unhealthy"

    async def check_all_services(self) -> dict[str, str]:
        """Check health of all downstream services."""
        stt, tts, brain = await asyncio.gather(
            self.check_service("stt", settings.stt_url),
            self.check_service("tts", settings.tts_url),
            self.check_service("brain", settings.brain_url),
        )
        return {"stt": stt, "tts": tts, "brain": brain}


def split_sentences(text: str) -> list[str]:
    """Split text at sentence boundaries for progressive TTS."""
    sentences = _SENTENCE_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


async def run_tool_loop(
    client: ServiceClient,
    initial_message: str,
    conversation_id: str | None,
    provider: str | None,
    max_iterations: int = 5,
) -> dict:
    """Run the agent tool-calling loop.

    Sends message to brain, checks for tool_calls, executes tools,
    sends results back, repeats until a text response is returned.
    """
    tools = get_tool_definitions() or None
    message = initial_message

    for i in range(max_iterations):
        result = await client.chat(
            message=message,
            conversation_id=conversation_id,
            provider=provider,
            tools=tools,
        )

        if result is None:
            return {"message": "I'm having trouble connecting to my brain. Please try again.", "conversation_id": conversation_id or ""}

        conversation_id = result.get("conversation_id", conversation_id)

        # If no tool calls, return the text response
        if not result.get("tool_calls"):
            return result

        # Execute tools and collect results
        tool_results = []
        for tc in result["tool_calls"]:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = json.loads(fn.get("arguments", "{}"))

            tool = get_tool_by_name(tool_name)
            if tool:
                try:
                    tool_result = await tool.execute(**tool_args)
                except Exception as e:
                    tool_result = f"Error executing {tool_name}: {e}"
            else:
                tool_result = f"Unknown tool: {tool_name}"

            tool_results.append(f"[{tool_name}]: {tool_result}")

        # Send tool results back as a new message
        message = "\n".join(tool_results)

    return {"message": result.get("message", ""), "conversation_id": conversation_id or ""}
