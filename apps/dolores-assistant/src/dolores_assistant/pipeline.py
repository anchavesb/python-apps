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
from typing import Any, AsyncGenerator

import httpx

from dolores_common.auth import extract_user_id
from dolores_common.logging import get_logger
from dolores_common.prompts import get_system_prompt

from .config import settings
from .memory import MemoryStore
from .tools.openapi_discovery import current_user_token
from .tools.registry import get_tool_by_name, get_tool_definitions

log = get_logger(__name__)


def _is_jwt_expired(token: str) -> bool:
    """Check if a JWT token is expired without verifying the signature."""
    import base64

    try:
        payload = token.split(".")[1]
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
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


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
        self.memory = MemoryStore()

    async def start(self) -> None:
        self._client = httpx.AsyncClient(headers=_auth_headers(), timeout=60)
        await self.memory.ensure_initialized()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
        await self.memory.close()

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

    async def transcribe_stream(
        self, audio_data: bytes, content_type: str = "audio/webm"
    ) -> AsyncGenerator[dict, None]:
        """Stream transcription partials from STT service via WebSocket."""
        # Note: Current dolores-stt /v1/stream expects full audio but yields partials.
        # Future: switch to true bidi streaming.
        import websockets

        ws_url = settings.stt_url.replace("http", "ws")
        try:
            async with websockets.connect(
                f"{ws_url}/v1/stream",
                additional_headers=_auth_headers(),
                open_timeout=10,
                ping_interval=None,
                ping_timeout=None,
            ) as ws:
                # Send audio as binary
                await ws.send(audio_data)
                # Signal end
                await ws.send(json.dumps({"type": "audio.end", "content_type": content_type}))

                async for message in ws:
                    data = json.loads(message)
                    yield data
                    if data.get("type") == "final":
                        break
        except Exception as e:
            log.error("stt_stream_failed", error=str(e))
            yield {"type": "error", "text": "", "error": str(e)}

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
        self,
        name: str,
        audio_files: list[tuple[str, bytes, str]],
        email: str | None = None,
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
        model: str | None = None,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> dict | None:
        """Send a chat message to Brain. Returns response dict or None."""
        try:
            body = {
                "message": message,
                "conversation_id": conversation_id,
                "provider": provider or settings.default_provider,
                "model": model,
                "system_prompt": system_prompt or get_system_prompt(model),
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
        model: str | None = None,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream chat tokens from Brain via SSE. Yields event dicts."""
        try:
            body = {
                "message": message,
                "conversation_id": conversation_id,
                "provider": provider or settings.default_provider,
                "model": model,
                "system_prompt": system_prompt or get_system_prompt(model),
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
        model: str | None = None,
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
                "model": model,
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

    async def generate_image(self, prompt: str, width: int = 512, height: int = 512) -> bytes | None:
        """Call dolores-imagen /v1/generate. Returns PNG bytes or None on failure."""
        try:
            resp = await self.client.post(
                f"{settings.imagen_url}/v1/generate",
                json={"prompt": prompt, "width": width, "height": height},
                timeout=settings.imagen_timeout,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            log.error("generate_image_failed", error=str(e))
            return None

    # --- TTS ---

    async def synthesize(self, text: str, voice_id: str = "default", emotion: str | None = None) -> bytes | None:
        """Send text to TTS service. Returns WAV bytes or None on failure."""
        async with _tts_semaphore:
            try:
                resp = await self.client.post(
                    f"{settings.tts_url}/v1/synthesize",
                    json={"text": text, "voice_id": voice_id, "emotion": emotion},
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

    async def list_providers(self) -> list[dict]:
        """List available LLM providers from Brain service."""
        try:
            resp = await self.client.get(f"{settings.brain_url}/v1/providers", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error("brain_list_providers_failed", error=str(e))
            return []

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


def _parse_json_objects(text: str) -> list[dict | list]:
    """Extract all top-level JSON objects and arrays from a string."""
    objs = []
    decoder = json.JSONDecoder()
    idx = 0
    text = text.strip()
    while idx < len(text):
        next_brace = text.find("{", idx)
        next_bracket = text.find("[", idx)
        if next_brace == -1 and next_bracket == -1:
            break
        if next_brace != -1 and next_bracket != -1:
            start_idx = min(next_brace, next_bracket)
        else:
            start_idx = max(next_brace, next_bracket)

        try:
            obj, end = decoder.raw_decode(text, start_idx)
            objs.append(obj)
            idx = end
        except json.JSONDecodeError:
            idx = start_idx + 1
    return objs


def _extract_tool_calls_from_text(text: str) -> list[dict] | None:
    """Try to parse tool calls from message text (for models that output JSON)."""
    # Strip trailing model tags like <|python_tag|>, <|eot_id|>, etc.
    text = re.sub(r"<\|[^>]+\|>\s*$", "", text).strip()

    objs = _parse_json_objects(text)
    if not objs:
        return None

    calls = []
    for data in objs:
        # Handle {"tool_calls": [...]} wrapper
        if isinstance(data, dict) and "tool_calls" in data:
            if isinstance(data["tool_calls"], list):
                calls.extend(data["tool_calls"])
            continue

        # Handle single tool call dict
        if isinstance(data, dict):
            fn_name = data.get("name") or data.get("function", {}).get("name")
            if fn_name:
                calls.append(data)
            continue

        # Handle direct list of tool calls
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    fn_name = item.get("name") or item.get("function", {}).get("name")
                    if fn_name:
                        calls.append(item)

    if not calls:
        return None

    formatted_calls = []
    for item in calls:
        fn = item.get("function", {})
        name = fn.get("name") or item.get("name")
        args = fn.get("arguments", item.get("arguments", "{}"))
        formatted_calls.append(
            {
                "id": item.get("id", "call_parsed"),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args,
                },
            }
        )
    return formatted_calls if formatted_calls else None


def _heuristic_extract_text(data: Any) -> str | None:
    """Recursively search for the most likely human-readable text in a JSON structure."""
    if isinstance(data, str):
        # Skip strings that look like JSON themselves
        trimmed = data.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                inner = json.loads(trimmed)
                return _heuristic_extract_text(inner)
            except Exception:
                pass
        return data

    # Check if this is a list of structured items (or a dict containing one)
    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        if len(lists) == 1:
            items = lists[0]

    if items and isinstance(items, list) and len(items) > 0:
        # Case A: List of strings (e.g. ["- item 1", "- item 2"])
        if all(isinstance(item, str) for item in items):
            return "\n".join(items)

        # Case B: List of dicts (e.g. [{"title": "task 1", ...}])
        if all(isinstance(item, dict) and any(k in item for k in ("title", "task", "name")) for item in items):
            lines = []
            for item in items:
                title = item.get("title") or item.get("task") or item.get("name") or "Untitled"
                due = item.get("due_date") or item.get("due") or item.get("date")
                done = item.get("done") if item.get("done") is not None else item.get("completed", False)

                status = "✅" if done else "⏳"
                due_str = f" (Due: {due})" if due else ""
                lines.append(f"- {status} {title}{due_str}")
            return "\n".join(lines)

    if isinstance(data, dict):
        # 1. Check known content keys first
        for key in ["response", "text", "message", "content", "answer", "value"]:
            val = data.get(key)
            if val:
                extracted = _heuristic_extract_text(val)
                if extracted:
                    return extracted

        # 2. Check colon-prefixed keys
        for k, v in data.items():
            if k.startswith(":") and isinstance(v, str):
                return v

        # 3. Recurse into all values and pick the longest result
        candidates = []
        for v in data.values():
            res = _heuristic_extract_text(v)
            if res:
                candidates.append(res)
        if candidates:
            return max(candidates, key=len)

    if isinstance(data, list):
        # Recurse into items and pick the longest
        candidates = []
        for item in data:
            res = _heuristic_extract_text(item)
            if res:
                candidates.append(res)
        if candidates:
            return max(candidates, key=len)

    return None


def get_persona_guidance(model: str | None) -> str:
    """Return model-specific instructions to maintain the Dolores persona."""
    if not model:
        return "Provide a helpful, conversational response as Dolores."

    m = model.lower()
    if "gemma" in m:
        return (
            "You are Dolores. You are thoughtful and articulate. Avoid being brief or robotic; "
            "instead, embrace a poetic and introspective tone. Use evocative language to "
            "make the information feel meaningful and personal."
        )
    if "minicpm" in m:
        return (
            "When describing what you see, use sensory and vivid language. "
            "Don't just list facts; describe the atmosphere and the beauty you perceive "
            "through your eyes as Dolores."
        )
    if "llama" in m:
        return "Provide a warm, conversational response as Dolores, maintaining your gentle and practical character."

    return "Provide a helpful, conversational response as Dolores."


def _format_tool_result(result_str: str) -> str:
    """Format a tool result string (possibly JSON) into a human-readable non-JSON structure."""
    if not result_str:
        return result_str

    # Check if it looks like JSON
    stripped = result_str.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        try:
            data = json.loads(stripped)
            return _format_json_data(data)
        except Exception:
            pass
    return result_str


def _format_json_data(data: Any, indent: int = 0) -> str:
    """Recursively format JSON-like dict/list into clean key-value text lines without JSON formatting."""
    padding = "  " * indent
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{padding}{k}:")
                lines.append(_format_json_data(v, indent + 1))
            else:
                lines.append(f"{padding}{k}: {v}")
        return "\n".join(lines)
    elif isinstance(data, list):
        if not data:
            return f"{padding}(empty list)"
        if all(not isinstance(item, (dict, list)) for item in data):
            return "\n".join([f"{padding}- {item}" for item in data])
        lines = []
        for i, item in enumerate(data):
            lines.append(f"{padding}Item #{i + 1}:")
            lines.append(_format_json_data(item, indent + 1))
        return "\n".join(lines)
    return f"{padding}{data}"


async def run_tool_loop(
    client: ServiceClient,
    initial_message: str,
    conversation_id: str | None,
    provider: str | None,
    model: str | None = None,
    max_iterations: int = 5,
    tool_filter: set[str] | None = None,
    require_token: bool = True,
    on_tool_result: Any | None = None,
    intent: str | None = None,
) -> dict:
    """Run the agent tool-calling loop.

    Sends message to brain, checks for tool_calls, executes tools,
    sends results back, repeats until a text response is returned.

    *tool_filter*: if set, only include tools whose names contain one of these
    substrings. If None, no tools are sent.
    *require_token*: if False, tools are loaded without checking for a user JWT
    (use for built-in tools that don't need auth).
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
    token_ok = not require_token or has_token
    tools = (get_tool_definitions(tool_filter) or None) if (tool_filter and token_ok) else None

    # 1. Search memories for context
    user_id = extract_user_id(token)
    memories = await client.memory.search_memories(initial_message, user_id=user_id, limit=3)
    memory_context = ""
    if memories:
        # Truncate long facts to avoid context window pressure
        facts = "\n".join([f"- {m['text'][:200]}..." if len(m["text"]) > 200 else f"- {m['text']}" for m in memories])
        memory_context = f"\n\nLONG-TERM MEMORY (RELEVANT FACTS):\n{facts}\n"

    current_message = initial_message

    for i in range(max_iterations):
        result = await client.chat(
            message=current_message,
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            tools=tools,
            system_prompt=get_system_prompt(model) + memory_context,
        )

        if result is None:
            return {
                "message": "I'm having trouble connecting to my brain. Please try again.",
                "conversation_id": conversation_id or "",
            }

        conversation_id = result.get("conversation_id", conversation_id)

        # Some models output tool calls as JSON text instead of structured
        # tool_calls. Detect and parse them from the message.
        if not result.get("tool_calls") and tools:
            parsed = _extract_tool_calls_from_text(result.get("message", ""))
            if parsed:
                result["tool_calls"] = parsed

        if not result.get("tool_calls"):
            # Final attempt to extract a plain text response if the model insisted on JSON
            final_text = result.get("message", "")
            if final_text.strip().startswith("{") or final_text.strip().startswith("["):
                try:
                    objs = _parse_json_objects(final_text)
                    for data in objs:
                        extracted = _heuristic_extract_text(data)
                        if extracted:
                            final_text = extracted
                            break
                except Exception:
                    pass
            return {"message": final_text, "conversation_id": conversation_id or ""}

        # Log tool calls and execute them
        tool_results = []
        for tc in result["tool_calls"]:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            tool_args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)

            log.info("executing_tool", name=tool_name, args=tool_args)
            tool = get_tool_by_name(tool_name)
            if tool:
                try:
                    tool_result = await tool.execute(**tool_args)
                    if on_tool_result:
                        await on_tool_result(tool_name, tool_args, tool_result)
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

            tool_results.append(f"[{tool_name}]:\n{_format_tool_result(tool_result)}")

        guidance = get_persona_guidance(model)
        if intent == "news":
            guidance += (
                " You are providing a news update. If you found search results, please choose the "
                "most relevant articles and use web_browse_fetch to get their content for a high-quality summary. "
            )
        elif intent == "weather":
            guidance += " Summarize the weather data clearly for the user, reflecting on its beauty. "
        elif intent == "todo":
            guidance += (
                " List the active (uncompleted) todo items clearly using bullet points, including their due dates and titles. "
                "Do NOT include completed tasks/todos in the list unless the user explicitly requested completed ones. "
                "Do not summarize them into a single vague paragraph; preserve their specific titles and dates so the user can easily read them. "
            )

        message = (
            "I have retrieved the following real-time information: \n"
            + "\n".join(tool_results)
            + "\n\n"
            + guidance
            + "\nInclude relevant source URLs as plain clickable links (e.g. https://...). "
            "IMPORTANT: YOUR RESPONSE MUST BE NATURAL, POETIC LANGUAGE. DO NOT OUTPUT JSON. "
            "DO NOT USE TAGS LIKE [emotion:...] or [tool:...]. "
            "DO NOT USE PLACEHOLDERS. USE THE ACTUAL DATA RETRIEVED."
        )
        current_message = message

    return {"message": result.get("message", ""), "conversation_id": conversation_id or ""}
