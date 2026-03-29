"""Pipeline orchestration: STT -> Brain -> TTS with graceful degradation.

Manages HTTP clients to downstream services, GPU concurrency control,
sentence-level TTS streaming, and the tool-calling agent loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import AsyncGenerator

import httpx

from dolores_common.logging import get_logger

from .config import settings
from .tools.openapi_discovery import current_user_token
from .tools.registry import get_tool_by_name, get_tool_definitions

log = get_logger(__name__)


def _is_jwt_expired(token: str) -> bool:
    """Check if a JWT token is expired without verifying the signature."""
    import base64
    try:
        # Decode the payload (second segment)
        payload = token.split(".")[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        if exp is None:
            return False
        return time.time() > exp
    except Exception:
        return False

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

    _EXT_MAP = {
        "audio/webm": ".webm",
        "audio/webm;codecs=opus": ".webm",
        "audio/mp4": ".mp4",
        "audio/aac": ".aac",
        "audio/ogg": ".ogg",
        "audio/ogg;codecs=opus": ".ogg",
    }

    async def transcribe(self, audio_data: bytes, content_type: str = "audio/webm") -> dict | None:
        """Send audio to STT service. Returns transcription dict or None on failure."""
        # Normalize: strip codec params (e.g. "audio/mp4;codecs=mp4a.40.2" -> "audio/mp4")
        base_type = content_type.split(";")[0].strip()
        ext = self._EXT_MAP.get(base_type, ".webm")
        filename = f"audio{ext}"
        async with _stt_semaphore:
            try:
                resp = await self.client.post(
                    f"{settings.stt_url}/v1/transcribe",
                    files={"file": (filename, audio_data, base_type)},
                    timeout=settings.stt_timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                log.error("stt_call_failed", error=str(e), audio_size=len(audio_data), content_type=content_type)
                return None

    # --- Speaker identification ---

    async def identify_speaker(self, audio_data: bytes, content_type: str) -> dict | None:
        """Send audio to STT /v1/identify endpoint. Returns {speaker_id, speaker_name, confidence}."""
        base_type = content_type.split(";")[0].strip()
        ext = self._EXT_MAP.get(base_type, ".webm")
        try:
            resp = await self.client.post(
                f"{settings.stt_url}/v1/identify",
                files={"file": (f"audio{ext}", audio_data, base_type)},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.warning("speaker_id_failed", error=str(e))
        return None

    # --- Speaker management (proxy to STT) ---

    async def list_speakers(self) -> list[dict]:
        """List enrolled speakers from STT service."""
        try:
            resp = await self.client.get(f"{settings.stt_url}/v1/speakers", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("list_speakers_failed", error=str(e))
            return []

    async def enroll_speaker(
        self, name: str, audio_files: list[tuple[str, bytes, str]], email: str | None = None,
    ) -> dict | None:
        """Enroll a new speaker via STT service."""
        try:
            files = [("files", (fname, data, ct)) for fname, data, ct in audio_files]
            params = {"name": name}
            if email:
                params["email"] = email
            resp = await self.client.post(
                f"{settings.stt_url}/v1/speakers",
                params=params,
                files=files,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("enroll_speaker_failed", error=str(e))
            return None

    async def delete_speaker(self, speaker_id: str) -> bool | None:
        """Delete a speaker profile via STT service.

        Returns True if deleted, False if not found, None on service error.
        """
        try:
            import uuid as _uuid
            _uuid.UUID(speaker_id, version=4)
        except ValueError:
            return False

        try:
            resp = await self.client.delete(f"{settings.stt_url}/v1/speakers/{speaker_id}", timeout=10)
            if resp.status_code == 204:
                return True
            if resp.status_code == 404:
                return False
            return None
        except Exception as e:
            log.error("delete_speaker_failed", error=str(e))
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

    # --- Image analysis ---

    async def analyze_image(
        self,
        text: str,
        image_data: str,
        conversation_id: str | None = None,
        provider: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream brain response for image analysis via /v1/chat/stream. Yields SSE event dicts.

        Handles the analyze_image intent: forwards image + text to the brain service which
        routes to a vision-capable provider (e.g. gemini-pro-vision, gpt-4o).
        """
        try:
            body = {
                "message": text,
                "image_data": image_data,
                "conversation_id": conversation_id,
                "provider": provider or settings.default_provider,
            }
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
            log.error("analyze_image_failed", error=str(e))
            yield {"type": "error", "error": str(e)}

    # --- Image generation ---

    async def generate_image(self, prompt: str) -> bytes | None:
        """Call dolores-imagen /v1/generate. Returns PNG bytes or None on failure."""
        try:
            resp = await self.client.post(
                f"{settings.imagen_url}/v1/generate",
                json={"prompt": prompt},
                timeout=settings.imagen_timeout,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            log.error("generate_image_failed", error=str(e))
            return None

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

    # --- Voice management ---

    async def list_voices(self) -> list[dict]:
        """Get voice profiles from TTS service."""
        try:
            resp = await self.client.get(f"{settings.tts_url}/v1/voices", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("tts_list_voices_failed", error=str(e))
            return []

    async def get_voice(self, voice_id: str) -> dict | None:
        """Get a single voice profile from TTS service."""
        try:
            resp = await self.client.get(f"{settings.tts_url}/v1/voices/{voice_id}", timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("tts_get_voice_failed", error=str(e))
            return None

    async def create_voice(self, name: str, audio_data: bytes, content_type: str, description: str = "") -> dict | None:
        """Create a voice profile via TTS service."""
        try:
            resp = await self.client.post(
                f"{settings.tts_url}/v1/voices",
                params={"name": name, "description": description},
                files={"file": ("reference.wav", audio_data, content_type)},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.error("tts_create_voice_failed", status=e.response.status_code, detail=e.response.text)
            return None
        except Exception as e:
            log.error("tts_create_voice_failed", error=str(e))
            return None

    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a voice profile via TTS service."""
        try:
            resp = await self.client.delete(f"{settings.tts_url}/v1/voices/{voice_id}", timeout=10)
            return resp.status_code == 204
        except Exception as e:
            log.error("tts_delete_voice_failed", error=str(e))
            return False

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


def _extract_tool_calls_from_text(text: str) -> list[dict] | None:
    """Try to parse tool calls from message text (for models that output JSON)."""
    text = text.strip()
    if not text.startswith("{") and not text.startswith("["):
        return None

    # Strip trailing model tags like <|python_tag|>, <|eot_id|>, etc.
    text = re.sub(r"<\|[^>]+\|>\s*$", "", text).rstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    # Handle {"tool_calls": [...]} wrapper
    if isinstance(data, dict) and "tool_calls" in data:
        data = data["tool_calls"]

    # Handle single tool call dict: {"name": "...", "arguments": {...}}
    if isinstance(data, dict) and data.get("name"):
        data = [data]

    # Handle direct list of tool calls
    if isinstance(data, list):
        calls = []
        for item in data:
            # Support both {"function": {"name": ...}} and {"name": ...} formats
            fn = item.get("function", {})
            name = fn.get("name") or item.get("name")
            if name:
                args = fn.get("arguments", item.get("arguments", "{}"))
                calls.append({
                    "id": item.get("id", "call_parsed"),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args,
                    },
                })
        return calls if calls else None

    return None


async def run_tool_loop(
    client: ServiceClient,
    initial_message: str,
    conversation_id: str | None,
    provider: str | None,
    max_iterations: int = 5,
    tool_filter: set[str] | None = None,
) -> dict:
    """Run the agent tool-calling loop.

    Sends message to brain, checks for tool_calls, executes tools,
    sends results back, repeats until a text response is returned.

    *tool_filter*: if set, only include tools whose names contain one of these
    substrings. If None, no tools are sent.
    """
    token = current_user_token.get()
    has_token = token is not None
    if has_token and _is_jwt_expired(token):
        log.warning("jwt_expired", message=initial_message[:80])
        return {
            "message": "Your session has expired. Please log in again.",
            "conversation_id": conversation_id or "",
            "session_expired": True,
        }
    tools = (get_tool_definitions(tool_filter) or None) if (tool_filter and has_token) else None
    message = initial_message

    # Use a fresh conversation for tool calls so stale history doesn't
    # confuse the LLM into generating text instead of calling tools.
    tool_conv_id = None

    for i in range(max_iterations):
        result = await client.chat(
            message=message,
            conversation_id=tool_conv_id,
            provider=provider,
            tools=tools,
        )

        if result is None:
            return {"message": "I'm having trouble connecting to my brain. Please try again.", "conversation_id": conversation_id or ""}

        tool_conv_id = result.get("conversation_id", tool_conv_id)

        # Some models output tool calls as JSON text instead of structured
        # tool_calls. Detect and parse them from the message.
        if not result.get("tool_calls") and tools:
            parsed = _extract_tool_calls_from_text(result.get("message", ""))
            if parsed:
                result["tool_calls"] = parsed

        # If no tool calls, return the text response
        if not result.get("tool_calls"):
            result["conversation_id"] = conversation_id or ""
            return result

        # Execute tools and collect results
        tool_results = []
        for tc in result["tool_calls"]:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            tool_args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)

            tool = get_tool_by_name(tool_name)
            if tool:
                try:
                    tool_result = await tool.execute(**tool_args)
                except PermissionError:
                    log.warning("tool_auth_failed", tool=tool_name)
                    return {
                        "message": "Your session has expired. Please log in again.",
                        "conversation_id": conversation_id or "",
                        "session_expired": True,
                    }
                except Exception as e:
                    tool_result = f"Error executing {tool_name}: {e}"
            else:
                tool_result = f"Unknown tool: {tool_name}"

            tool_results.append(f"[{tool_name}]: {tool_result}")

        # Send tool results back as a new message (without tools, so LLM
        # generates a natural language response instead of more tool calls)
        message = "\n".join(tool_results)
        tools = None

    return {"message": result.get("message", ""), "conversation_id": conversation_id or ""}
