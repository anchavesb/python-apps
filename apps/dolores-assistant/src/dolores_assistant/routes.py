"""Assistant API routes: WS /v1/conversation, POST /v1/chat, voice & speaker management."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from dolores_common.auth import ClientAPIKey, validate_ws_token
from dolores_common.logging import get_logger

from .config import settings
from .intent import classify_intent
from .pipeline import ServiceClient, run_tool_loop, split_sentences
from .schemas import TextChatRequest, TextChatResponse
from .tools.openapi_discovery import current_user_token
from .tools.registry import get_tool_definitions

SPEAKER_NAME_RE = re.compile(r"^[a-zA-Z0-9 ]{1,32}$")
_SPEAKER_TAG_RE = re.compile(r"^\[Speaker:[^\]]+\]\s*")
_VOCATIVE_RE = re.compile(r"^dolores,?\s*", re.IGNORECASE)

_SPEAKER_CONFIDENCE_THRESHOLD = 0.70


def _strip_for_intent(text: str) -> str:
    """Strip [Speaker: X] prefix and leading vocative address before intent classification."""
    text = _SPEAKER_TAG_RE.sub("", text)
    text = _VOCATIVE_RE.sub("", text)
    return text.strip()

log = get_logger(__name__)


def inject_speaker_context(
    user_text: str,
    speaker_result: dict | None,
    threshold: float = _SPEAKER_CONFIDENCE_THRESHOLD,
) -> str:
    """Prepend [Speaker: Name] tag to user text when identification is confident.

    Returns the original text unmodified if speaker_result is None, confidence
    is below threshold, or the name fails sanitization.
    """
    if not speaker_result or not speaker_result.get("speaker_name"):
        return user_text
    name = speaker_result["speaker_name"]
    confidence = speaker_result.get("confidence", 0)
    if confidence >= threshold and SPEAKER_NAME_RE.match(name):
        log.info("speaker_id_applied", name=name, confidence=confidence)
        return f"[Speaker: {name}] {user_text}"

    if confidence < threshold:
        log.info("speaker_id_low_confidence", name=name, confidence=confidence, threshold=threshold)
    elif not SPEAKER_NAME_RE.match(name):
        log.warning("speaker_id_invalid_name", name=name)
    return user_text


router = APIRouter(prefix="/v1", tags=["assistant"])

_service_client: ServiceClient | None = None


def get_service_client() -> ServiceClient:
    if _service_client is None:
        raise HTTPException(status_code=503, detail="Service client not initialized")
    return _service_client


def set_service_client(client: ServiceClient) -> None:
    global _service_client
    _service_client = client


@router.get("/settings")
async def get_backend_settings():
    """Expose backend defaults to frontend."""
    return {
        "default_provider": settings.default_provider,
        "default_voice_id": settings.default_voice_id,
    }


@router.post("/chat", response_model=TextChatResponse)
async def text_chat(
    req: TextChatRequest,
    request: Request,
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
) -> TextChatResponse:
    """Text-only chat endpoint (simpler alternative to WebSocket)."""
    # Forward user's OIDC JWT to downstream services (e.g. todo API).
    # Uses X-User-Token to avoid conflict with Authorization (used for API key auth).
    user_jwt = request.headers.get("x-user-token", "")
    token = current_user_token.set(user_jwt or None)
    try:
        tool_filter = _detect_tool_filter(req.message) if user_jwt else None
        result = await run_tool_loop(
            client=client,
            initial_message=req.message,
            conversation_id=req.conversation_id,
            provider=req.provider,
            tool_filter=tool_filter,
        )

        return TextChatResponse(
            message=result.get("message", ""),
            conversation_id=result.get("conversation_id", ""),
        )
    finally:
        current_user_token.reset(token)


# --- Voice management (proxy to TTS service) ---


@router.get("/voices")
async def list_voices(
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """List available voice profiles (proxies to TTS service)."""
    return await client.list_voices()


@router.get("/voices/{voice_id}")
async def get_voice(
    voice_id: str,
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """Get a voice profile (proxies to TTS service)."""
    result = await client.get_voice(voice_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Voice not found")
    return result


@router.post("/voices")
async def create_voice(
    name: str,
    file: UploadFile,
    description: str = "",
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """Create a voice profile (proxies to TTS service)."""
    audio_data = await file.read()
    result = await client.create_voice(
        name=name,
        audio_data=audio_data,
        content_type=file.content_type or "audio/wav",
        description=description,
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Failed to create voice profile")
    return result


@router.delete("/voices/{voice_id}", status_code=204)
async def delete_voice(
    voice_id: str,
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """Delete a voice profile (proxies to TTS service)."""
    success = await client.delete_voice(voice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Voice not found")
    return Response(status_code=204)


# --- Speaker management (proxy to STT service) ---


@router.get("/speakers")
async def list_speakers(
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """List enrolled speaker profiles (proxies to STT service)."""
    return await client.list_speakers()


@router.post("/speakers")
async def enroll_speaker(
    name: str,
    files: list[UploadFile],
    email: str | None = None,
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """Enroll a new speaker (proxies to STT service)."""
    audio_files = []
    for f in files:
        data = await f.read()
        if data:
            audio_files.append((f.filename or "audio.webm", data, f.content_type or "audio/webm"))

    if not audio_files:
        raise HTTPException(status_code=400, detail="No audio files provided")

    result = await client.enroll_speaker(name=name, audio_files=audio_files, email=email)
    if result is None:
        raise HTTPException(status_code=502, detail="Failed to enroll speaker")
    return result


@router.delete("/speakers/{speaker_id}", status_code=204)
async def delete_speaker(
    speaker_id: str,
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """Delete a speaker profile (proxies to STT service)."""
    result = await client.delete_speaker(speaker_id)
    if result is None:
        raise HTTPException(status_code=502, detail="Speaker service unavailable")
    if not result:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return Response(status_code=204)


# --- WebSocket conversation ---


@router.websocket("/conversation")
async def conversation_ws(websocket: WebSocket) -> None:
    """Full-duplex WebSocket for voice + text conversation.

    Protocol:
    Client -> Server:
      JSON: {type: "session.start", voice_id, provider, mode, token, conversation_id?}
      JSON: {type: "audio.start"}
      Binary: audio chunks
      JSON: {type: "audio.end"}
      JSON: {type: "text.send", text: "..."}
      JSON: {type: "session.end"}

    Server -> Client:
      JSON: {type: "session.created", session_id, conversation_id}
      JSON: {type: "transcription.partial", text}
      JSON: {type: "transcription.final", text}
      JSON: {type: "response.text", content}
      Binary: TTS audio chunks
      JSON: {type: "response.end", full_text}
      JSON: {type: "error", code, message}
    """
    await websocket.accept()

    client = _service_client
    if client is None:
        await websocket.send_json({"type": "error", "code": "service_unavailable", "message": "Service not ready"})
        await websocket.close()
        return

    session_id = str(uuid.uuid4())
    conversation_id = None
    voice_id = settings.default_voice_id
    provider = settings.default_provider
    mode = "both"
    audio_buffer = bytearray()
    _cv_token = current_user_token.set(None)

    try:
        # Wait for session.start
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != "session.start":
            await websocket.send_json({"type": "error", "code": "protocol_error", "message": "Expected session.start"})
            await websocket.close()
            return

        # Validate API key
        await validate_ws_token(websocket)

        voice_id = msg.get("voice_id", voice_id)
        provider = msg.get("provider", provider)
        mode = msg.get("mode", mode)
        conversation_id = msg.get("conversation_id") or str(uuid.uuid4())

        # Capture user's OIDC JWT for forwarding to downstream services (e.g. todo API)
        # Separate from "token" which is the API key for assistant auth
        _cv_token = current_user_token.set(msg.get("user_token"))

        await websocket.send_json(
            {
                "type": "session.created",
                "session_id": session_id,
                "conversation_id": conversation_id,
            }
        )

        log.info("session_started", session_id=session_id, mode=mode, provider=provider)

        # Main message loop
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                log.info("ws_client_disconnected", session_id=session_id)
                break

            if "bytes" in message:
                # Accumulate audio chunks
                audio_buffer.extend(message["bytes"])
                continue

            if "text" not in message:
                continue

            data = json.loads(message["text"])
            msg_type = data.get("type", "")

            if msg_type == "session.end":
                break

            elif msg_type == "audio.start":
                audio_buffer = bytearray()

            elif msg_type == "audio.end":
                # Grab buffer and reset immediately to avoid stale data
                audio_data = bytes(audio_buffer)
                audio_buffer = bytearray()
                content_type = data.get("content_type", "audio/webm")

                if not audio_data:
                    await websocket.send_json(
                        {"type": "error", "code": "no_audio", "message": "No audio data received"}
                    )
                    continue

                # Validate audio magic bytes
                valid = False
                if len(audio_data) >= 4:
                    header = audio_data[:4]
                    # WebM/MKV (EBML): 0x1A45DFA3
                    if header == b"\x1a\x45\xdf\xa3":
                        valid = True
                    # MP4/M4A (ftyp): bytes 4-7 are 'ftyp' but byte 0-3 is box size
                    elif len(audio_data) >= 8 and audio_data[4:8] == b"ftyp":
                        valid = True
                    # OGG: 'OggS'
                    elif header == b"OggS":
                        valid = True

                if not valid:
                    log.warning(
                        "unrecognized_audio_header",
                        size=len(audio_data),
                        header=audio_data[:8].hex() if len(audio_data) >= 8 else audio_data.hex(),
                        content_type=content_type,
                    )
                    # Still attempt transcription — let STT service decide

                # STT + Speaker ID in parallel
                transcription, speaker_result = await asyncio.gather(
                    client.transcribe(audio_data, content_type=content_type),
                    client.identify_speaker(audio_data, content_type=content_type),
                    return_exceptions=True,
                )
                # Handle exceptions gracefully — speaker failure doesn't block transcription
                if isinstance(transcription, Exception):
                    transcription = None
                if isinstance(speaker_result, Exception):
                    speaker_result = None

                if transcription is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "stt_unavailable",
                            "message": "Speech recognition failed, please type instead",
                        }
                    )
                    continue

                user_text = transcription.get("text", "")

                # Enrich transcription.final with speaker info
                final_event = {"type": "transcription.final", "text": user_text}
                if speaker_result and speaker_result.get("speaker_name"):
                    final_event["speaker_name"] = speaker_result["speaker_name"]
                    final_event["speaker_confidence"] = speaker_result.get("confidence", 0)
                await websocket.send_json(final_event)

                if not user_text.strip():
                    continue

                # Inject speaker context into message for Brain (sanitized)
                brain_text = inject_speaker_context(user_text, speaker_result)

                # Brain -> response
                await _process_and_respond(websocket, client, brain_text, conversation_id, provider, voice_id, mode)

            elif msg_type == "session.update":
                if "mode" in data:
                    mode = data["mode"]
                    log.info("session_mode_updated", session_id=session_id, mode=mode)
                continue

            elif msg_type == "session.update_token":
                new_token = data.get("user_token")
                _cv_token = current_user_token.set(new_token)
                log.info("token_updated", session_id=session_id)
                continue

            elif msg_type == "text.send":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                await _process_and_respond(websocket, client, user_text, conversation_id, provider, voice_id, mode)

            elif msg_type == "image.send":
                user_text = data.get("text", "").strip() or "Describe this image."
                image_data = data.get("image_data", "")
                if not image_data:
                    await websocket.send_json(
                        {"type": "error", "code": "no_image", "message": "No image data provided"}
                    )
                    continue
                await _process_image_message(
                    websocket, client, user_text, image_data, conversation_id, provider, voice_id, mode
                )

    except WebSocketDisconnect:
        log.info("ws_disconnected", session_id=session_id)
    except Exception as e:
        log.error("ws_error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "code": "internal_error", "message": str(e)})
        except Exception:
            pass
    finally:
        current_user_token.reset(_cv_token)


_EMOTION_TAG_RE = re.compile(r"^\[emotion:(\w+)\]\s*")
_VALID_EMOTIONS = {"happy", "sad", "angry", "neutral"}
_RENDER_MODE_RE = re.compile(r"\b(show|open|fetch|give me the page|display|load|go to|navigate to)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")


def _is_render_mode(text: str) -> bool:
    """Return True when the user wants raw results/page displayed rather than summarized."""
    return bool(_RENDER_MODE_RE.search(text)) or bool(_URL_RE.search(text))


async def _process_image_message(
    websocket: WebSocket,
    client: ServiceClient,
    user_text: str,
    image_data: str,
    conversation_id: str | None,
    provider: str,
    voice_id: str,
    mode: str,
) -> None:
    """Forward image + text to brain for analysis, stream response back to client."""
    full_text = ""
    async for event in client.analyze_image(
        text=user_text,
        image_data=image_data,
        conversation_id=conversation_id,
        provider=provider,
    ):
        if event.get("type") == "token":
            content = event.get("content", "")
            full_text += content
            await websocket.send_json({"type": "response.text", "content": content})
        elif event.get("type") == "done":
            full_text = event.get("content", full_text)
        elif event.get("type") == "error":
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "brain_error",
                    "message": event.get("error", "Unknown error"),
                }
            )
            return

    if mode != "text" and full_text.strip():
        sentences = split_sentences(full_text)
        for sentence in sentences:
            audio = await client.synthesize(sentence, voice_id=voice_id)
            if audio:
                await websocket.send_bytes(audio)

    await websocket.send_json({"type": "response.end", "full_text": full_text})


def _detect_tool_filter(message: str) -> set[str] | None:
    """Classify message intent and return tool name filter, or None for chat."""
    _, tool_filter, _ = classify_intent(_strip_for_intent(message))
    return tool_filter


async def _process_web_browse_render(websocket: WebSocket, user_text: str) -> None:
    """Render-mode web browse: run tools directly and emit response.web_results.

    If the message contains a URL, fetches that page; otherwise runs a search.
    Skips Brain — results go straight to the frontend as structured JSON.
    """
    from .tools.registry import get_tool_by_name

    url_match = _URL_RE.search(user_text)

    if url_match:
        url = url_match.group(0).rstrip(".,;)")
        tool = get_tool_by_name("web_browse_fetch")
        if tool is None:
            await websocket.send_json(
                {"type": "error", "code": "tool_unavailable", "message": "Page fetch tool not available"}
            )
            await websocket.send_json({"type": "response.end", "full_text": ""})
            return
        await websocket.send_json({"type": "response.text", "content": f"Fetching {url}..."})
        page_content = await tool.execute(url=url)
        await websocket.send_json(
            {
                "type": "response.web_results",
                "page_content": page_content,
                "url": url,
            }
        )
    else:
        # Strip common browse keywords to extract the bare query
        query = (
            re.sub(
                r"^\s*(browse|search the web for|search for|look up|find|google|web search|search online for)\s+",
                "",
                user_text,
                flags=re.IGNORECASE,
            ).strip()
            or user_text
        )

        tool = get_tool_by_name("web_browse_search")
        if tool is None:
            await websocket.send_json(
                {"type": "error", "code": "tool_unavailable", "message": "Web search tool not available"}
            )
            await websocket.send_json({"type": "response.end", "full_text": ""})
            return
        await websocket.send_json({"type": "response.text", "content": f'Searching for "{query}"...'})
        raw = await tool.execute(query=query)
        try:
            import json as _json

            results = _json.loads(raw)
        except Exception:
            results = []
        await websocket.send_json(
            {
                "type": "response.web_results",
                "results": results,
                "query": query,
            }
        )

    await websocket.send_json({"type": "response.end", "full_text": ""})


async def _process_web_browse_verbal(
    websocket: WebSocket,
    client: ServiceClient,
    user_text: str,
    conversation_id: str | None,
    provider: str,
    voice_id: str,
    mode: str,
) -> None:
    """Verbal web browse: call tool directly, then ask Brain to summarize results."""
    from .tools.registry import get_tool_by_name

    url_match = _URL_RE.search(user_text)

    if url_match:
        url = url_match.group(0).rstrip(".,;)")
        tool = get_tool_by_name("web_browse_fetch")
        if tool is None:
            await websocket.send_json(
                {"type": "error", "code": "tool_unavailable", "message": "Page fetch tool not available"}
            )
            await websocket.send_json({"type": "response.end", "full_text": ""})
            return
        page_content = await tool.execute(url=url)
        summary_prompt = (
            f"The user asked: {user_text}\n\n"
            f"Here is the content fetched from {url}:\n\n{page_content}\n\n"
            "Please summarize the key information from this page in response to the user's request."
        )
    else:
        search_tool = get_tool_by_name("web_browse_search")
        fetch_tool = get_tool_by_name("web_browse_fetch")
        if search_tool is None:
            await websocket.send_json(
                {"type": "error", "code": "tool_unavailable", "message": "Web search tool not available"}
            )
            await websocket.send_json({"type": "response.end", "full_text": ""})
            return

        raw = await search_tool.execute(query=user_text)

        # Try to fetch the top result for actual content, not just snippets
        page_content = ""
        if fetch_tool is not None:
            try:
                import json as _json

                results = _json.loads(raw)
                if results and results[0].get("url"):
                    page_content = await fetch_tool.execute(url=results[0]["url"])
            except Exception:
                pass

        context = f"Search results:\n{raw}"
        if page_content and not page_content.startswith("Failed"):
            context += f"\n\nTop result page content:\n{page_content}"

        summary_prompt = (
            f"The user asked: {user_text}\n\n"
            f"Here is live data retrieved from the web:\n\n{context}\n\n"
            "Using only the information above, answer the user's question concisely. "
            "Do not say you cannot browse the internet — the data is already provided."
        )

    log.info("web_browse_summary_prompt", prompt=summary_prompt[:300])
    result = await client.chat(
        message=summary_prompt,
        conversation_id=None,
        provider=provider,
    )
    full_text = result.get("message", "") if result else ""

    if full_text:
        await websocket.send_json({"type": "response.text", "content": full_text})
    if mode != "text" and full_text.strip():
        sentences = split_sentences(full_text)
        for sentence in sentences:
            audio = await client.synthesize(sentence, voice_id=voice_id)
            if audio:
                await websocket.send_bytes(audio)
    await websocket.send_json({"type": "response.end", "full_text": full_text})


async def _process_and_respond(
    websocket: WebSocket,
    client: ServiceClient,
    user_text: str,
    conversation_id: str | None,
    provider: str,
    voice_id: str,
    mode: str,
) -> None:
    """Send user text to brain, stream response text, and optionally TTS audio."""
    try:
        intent_name, tool_filter, confidence = classify_intent(_strip_for_intent(user_text))
    except Exception:
        intent_name, tool_filter, confidence = None, None, 0.0

    log.info("intent_dispatch", message=user_text[:80], intent=intent_name, confidence=round(confidence, 3))

    if intent_name == "generate_image":
        await websocket.send_json({"type": "response.text", "content": "Generating your image..."})
        # Use 512x512 for better performance on Metal
        image_bytes = await client.generate_image(user_text, width=512, height=512)
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode()
            await websocket.send_json(
                {
                    "type": "response.image",
                    "image_data": f"data:image/png;base64,{image_b64}",
                    "prompt": user_text,
                }
            )
        else:
            await websocket.send_json(
                {
                    "type": "response.text",
                    "content": "I wasn't able to generate the image. Please try again.",
                }
            )
        await websocket.send_json({"type": "response.end", "full_text": ""})
        return

    if intent_name == "web_browse" and _is_render_mode(user_text):
        await _process_web_browse_render(websocket, user_text)
        return

    if intent_name == "web_browse":
        await _process_web_browse_verbal(websocket, client, user_text, conversation_id, provider, voice_id, mode)
        return

    has_user_token = current_user_token.get() is not None
    if tool_filter and has_user_token and get_tool_definitions(tool_filter):
        result = await run_tool_loop(
            client=client,
            initial_message=user_text,
            conversation_id=conversation_id,
            provider=provider,
            tool_filter=tool_filter,
        )

        # Handle session expiry with a dedicated event so the UI can prompt re-login
        if result.get("session_expired"):
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "session_expired",
                    "message": result.get("message", "Your session has expired."),
                }
            )
            return

        full_text = result.get("message", "")
        emotion = None

        # Parse and strip emotion tag
        m = _EMOTION_TAG_RE.match(full_text)
        if m:
            emotion = m.group(1)
            if emotion in _VALID_EMOTIONS:
                log.info("emotion_parsed", emotion=emotion)
                await websocket.send_json({"type": "response.emotion", "emotion": emotion})
            else:
                log.warning("invalid_emotion_tag", emotion=emotion)
                emotion = None
            full_text = full_text[m.end() :]
        else:
            log.info("no_emotion_tag_found", text=full_text[:50])

        if full_text:
            await websocket.send_json({"type": "response.text", "content": full_text})

        # TTS
        if mode != "text" and full_text.strip():
            sentences = split_sentences(full_text)
            for sentence in sentences:
                audio = await client.synthesize(sentence, voice_id=voice_id, emotion=emotion)
                if audio:
                    await websocket.send_bytes(audio)

        await websocket.send_json({"type": "response.end", "full_text": full_text})
        return

    # No tools — use streaming path for faster response
    full_text = ""
    emotion: str | None = None
    emotion_parsed = False
    emotion_buffer = ""  # Buffer initial tokens to detect emotion tag

    async for event in client.chat_stream(
        message=user_text,
        conversation_id=conversation_id,
        provider=provider,
    ):
        if event.get("type") == "token":
            content = event.get("content", "")

            if not emotion_parsed:
                # Buffer tokens until we can check for emotion tag
                emotion_buffer += content
                match = _EMOTION_TAG_RE.match(emotion_buffer)
                if match:
                    _candidate = match.group(1)
                    if _candidate in _VALID_EMOTIONS:
                        emotion = _candidate
                        log.info("emotion_parsed_stream", emotion=emotion)
                        await websocket.send_json({"type": "response.emotion", "emotion": emotion})
                    else:
                        log.warning("invalid_emotion_tag_stream", emotion=_candidate)
                    # Strip the tag and send the remainder
                    remainder = emotion_buffer[match.end() :]
                    emotion_parsed = True
                    if remainder:
                        full_text += remainder
                        await websocket.send_json({"type": "response.text", "content": remainder})
                elif len(emotion_buffer) > 30:
                    # No tag found within first 30 chars, flush buffer
                    emotion_parsed = True
                    full_text += emotion_buffer
                    await websocket.send_json({"type": "response.text", "content": emotion_buffer})
            else:
                full_text += content
                await websocket.send_json({"type": "response.text", "content": content})

        elif event.get("type") == "done":
            full_text = event.get("content", full_text)
            # Strip emotion tag from final text if present
            m = _EMOTION_TAG_RE.match(full_text)
            if m:
                full_text = full_text[m.end() :]

        elif event.get("type") == "error":
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "brain_error",
                    "message": event.get("error", "Unknown error"),
                }
            )
            return

    # Flush any remaining buffer (short responses)
    if not emotion_parsed and emotion_buffer:
        match = _EMOTION_TAG_RE.match(emotion_buffer)
        if match:
            _candidate = match.group(1)
            if _candidate in _VALID_EMOTIONS:
                emotion = _candidate
                log.info("emotion_parsed_stream_flush", emotion=emotion)
                await websocket.send_json({"type": "response.emotion", "emotion": emotion})
            else:
                log.warning("invalid_emotion_tag_stream_flush", emotion=_candidate)
            remainder = emotion_buffer[match.end() :]
            if remainder:
                full_text = remainder
                await websocket.send_json({"type": "response.text", "content": remainder})
        else:
            full_text = emotion_buffer
            await websocket.send_json({"type": "response.text", "content": emotion_buffer})

    # TTS: synthesize sentences and send audio
    if mode != "text" and full_text.strip():
        sentences = split_sentences(full_text)
        for sentence in sentences:
            audio = await client.synthesize(sentence, voice_id=voice_id, emotion=emotion)
            if audio:
                await websocket.send_bytes(audio)

    await websocket.send_json({"type": "response.end", "full_text": full_text})
