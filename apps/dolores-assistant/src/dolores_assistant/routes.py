"""Assistant API routes: WS /v1/conversation, POST /v1/chat, voice & speaker management."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from dolores_common.auth import ClientAPIKey, validate_oidc_token, validate_ws_token
from dolores_common.logging import get_logger

from .config import settings
from .intent import classify_intent
from .pipeline import ServiceClient, run_tool_loop, split_sentences
from .schemas import TextChatRequest, TextChatResponse
from .tools.openapi_discovery import current_user_token

SPEAKER_NAME_RE = re.compile(r"^[a-zA-Z0-9 ]{1,32}$")

_SPEAKER_CONFIDENCE_THRESHOLD = 0.70

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

_NO_TOKEN_INTENTS = frozenset({"web_browse", "weather", "news"})

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
        "default_model": getattr(settings, "default_model", "llama3.2"),
        "default_voice_id": settings.default_voice_id,
    }


@router.get("/providers")
async def list_providers(
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
):
    """List available LLM providers (proxies to Brain service)."""
    return await client.list_providers()


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
    user_jwt = request.headers.get("x-user-token", "") or settings.default_user_token
    token = current_user_token.set(user_jwt or None)
    try:
        intent_name, tool_filter, _ = classify_intent(req.message)

        if intent_name == "generate_image":
            image_bytes = await client.generate_image(req.message, width=512, height=512)
            if image_bytes:
                image_b64 = base64.b64encode(image_bytes).decode()
                full_text = f"Generating your image...\n\n![Generated Image](data:image/png;base64,{image_b64})"
            else:
                full_text = "I wasn't able to generate the image."
            return TextChatResponse(
                message=full_text,
                conversation_id=req.conversation_id or str(uuid.uuid4()),
            )

        require_token = intent_name not in _NO_TOKEN_INTENTS

        result = await run_tool_loop(
            client=client,
            initial_message=req.message,
            conversation_id=req.conversation_id,
            provider=req.provider,
            model=req.model,
            tool_filter=tool_filter,
            require_token=require_token,
            intent=intent_name,
        )

        _, full_text = _sanitize_response(result.get("message", ""))

        return TextChatResponse(
            message=full_text,
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


# --- Conversation (Main WebSocket) ---


@router.websocket("/conversation")
async def conversation_ws(websocket: WebSocket) -> None:
    """Bidi streaming conversation: Audio/Text in -> Emotion/Text/Audio/Structured out."""
    await websocket.accept()

    # Validate API key
    await validate_ws_token(websocket)

    # Get client from app state (injected via main lifespan)
    client = get_service_client()

    # Initial session state
    conversation_id: str | None = None
    provider: str = settings.default_provider
    model: str | None = None
    voice_id: str = settings.default_voice_id
    mode: str = "audio"  # 'audio' or 'text'

    session_id = str(uuid.uuid4())
    log.info("ws_connected", session_id=session_id)

    audio_buffer = bytearray()
    _initial_cv_token = current_user_token.set(settings.default_user_token)

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message:
                audio_buffer.extend(message["bytes"])
                continue

            if "text" not in message:
                continue

            data = json.loads(message["text"])
            msg_type = data.get("type")

            if msg_type == "session.start":
                if "provider" in data:
                    provider = data["provider"]
                if "model" in data:
                    model = data["model"]
                if "voice_id" in data:
                    voice_id = data["voice_id"]
                if "mode" in data:
                    mode = data["mode"]
                if "conversation_id" in data:
                    conversation_id = data["conversation_id"]

                # Set active user token for isolated database and tool calls.
                # Validate the token signature if OIDC is enabled to prevent
                # identity spoofing via crafted JWT payloads.
                user_token = (
                    data.get("user_token") or websocket.query_params.get("token") or settings.default_user_token
                )
                if user_token and os.environ.get("OIDC_ENABLED", "0") == "1":
                    # validate_oidc_token may do synchronous HTTP I/O (JWKS fetch),
                    # so run it in a thread to avoid blocking the event loop.
                    if not await asyncio.to_thread(validate_oidc_token, user_token):
                        await websocket.send_json({"type": "error", "message": "Invalid or expired user token"})
                        await websocket.close(code=4403)
                        return
                current_user_token.set(user_token)

                # Acknowledge session start and send IDs back to client
                # conversation_id might be None, in which case the frontend gets a placeholder
                await websocket.send_json(
                    {
                        "type": "session.created",
                        "session_id": session_id,
                        "conversation_id": conversation_id or str(uuid.uuid4()),
                    }
                )
                continue

            elif msg_type == "audio.start":
                audio_buffer = bytearray()

            elif msg_type == "audio.end":
                audio_data = bytes(audio_buffer)
                audio_buffer = bytearray()
                content_type = data.get("content_type", "audio/webm")
                if not audio_data:
                    continue

                # Start Speaker ID in background
                speaker_task = asyncio.create_task(client.identify_speaker(audio_data, content_type=content_type))

                try:
                    # Stream transcription partials
                    user_text = ""
                    async for chunk in client.transcribe_stream(audio_data, content_type=content_type):
                        if chunk["type"] == "partial":
                            await websocket.send_json({"type": "transcription.partial", "text": chunk["text"]})
                        elif chunk["type"] == "final":
                            user_text = chunk["text"]
                        elif chunk["type"] == "error":
                            await websocket.send_json({"type": "error", "code": "stt_error", "message": chunk["error"]})
                            break

                    if not user_text:
                        continue

                    # Wait for speaker ID
                    try:
                        speaker_result = await speaker_task
                    except Exception:
                        speaker_result = None

                    # Enrich transcription.final with speaker info
                    final_event = {"type": "transcription.final", "text": user_text}
                    if speaker_result and speaker_result.get("speaker_name"):
                        final_event["speaker_name"] = speaker_result["speaker_name"]
                        final_event["speaker_confidence"] = speaker_result.get("confidence", 0)
                    await websocket.send_json(final_event)

                    if not user_text.strip():
                        continue

                    # Inject speaker context
                    brain_text = inject_speaker_context(user_text, speaker_result)

                    # Brain -> response
                    await _process_and_respond(
                        websocket, client, brain_text, conversation_id, provider, model, voice_id, mode
                    )
                finally:
                    if not speaker_task.done():
                        speaker_task.cancel()
                        try:
                            await speaker_task
                        except asyncio.CancelledError:
                            pass

            elif msg_type == "session.update":
                if "mode" in data:
                    mode = data["mode"]
                if "voice_id" in data:
                    voice_id = data["voice_id"]
                if "provider" in data:
                    provider = data["provider"]
                if "model" in data:
                    model = data["model"]
                continue

            elif msg_type == "session.update_token":
                new_token = data.get("user_token") or settings.default_user_token
                # Validate token signature if OIDC is enabled to prevent
                # mid-session identity spoofing via a crafted JWT swap.
                # Run in a thread to avoid blocking the event loop on JWKS I/O.
                if new_token and os.environ.get("OIDC_ENABLED", "0") == "1":
                    if not await asyncio.to_thread(validate_oidc_token, new_token):
                        await websocket.send_json({"type": "error", "message": "Invalid or expired user token"})
                        await websocket.close(code=4403)
                        return
                current_user_token.set(new_token)
                continue

            elif msg_type == "text.send":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue
                await _process_and_respond(
                    websocket, client, user_text, conversation_id, provider, model, voice_id, mode
                )

            elif msg_type == "image.send":
                user_text = data.get("text", "").strip() or "Describe this image."
                image_data = data.get("image_data", "")
                if not image_data:
                    continue
                await _process_image_message(
                    websocket, client, user_text, image_data, conversation_id, provider, model, voice_id, mode
                )

    except WebSocketDisconnect:
        log.info("ws_disconnected", session_id=session_id)
    except Exception as e:
        log.error("ws_error", error=str(e))
    finally:
        if _initial_cv_token:
            try:
                current_user_token.reset(_initial_cv_token)
            except ValueError:
                pass


_EMOTION_TAG_RE = re.compile(r"\[emotion:(\w+)\]")
_TOOL_TAG_RE = re.compile(r"\[(tool|news):[\w_]+\]")
_VALID_EMOTIONS = {"happy", "sad", "angry", "neutral"}


def _extract_emotion_and_clean(text: str) -> tuple[str | None, str]:
    """Capture the first valid emotion tag and strip ALL technical tags from the string."""
    # Find the first valid emotion to use for UI/TTS
    emotion = None
    all_emotions = _EMOTION_TAG_RE.findall(text)
    for cand in all_emotions:
        if cand in _VALID_EMOTIONS:
            emotion = cand
            break

    # Strip all [emotion:...] tags globally
    text = _EMOTION_TAG_RE.sub("", text)
    # Strip all [tool:...] or [news:...] tags globally
    text = _TOOL_TAG_RE.sub("", text)

    return emotion, text.strip()


def _sanitize_response(text: str) -> tuple[str | None, str]:
    """Strip emotion/tool tags and extract plain text from JSON if the model returned JSON.

    Returns (emotion, clean_text).
    """
    emotion, text = _extract_emotion_and_clean(text)
    if text.strip().startswith(("{", "[")):
        try:
            from .pipeline import _heuristic_extract_text, _parse_json_objects

            objs = _parse_json_objects(text)
            for data in objs:
                extracted = _heuristic_extract_text(data)
                if extracted:
                    _, text = _extract_emotion_and_clean(extracted)
                    break
        except Exception:
            pass
    return emotion, text


async def _synthesize_and_send(
    websocket: WebSocket,
    client: ServiceClient,
    text: str,
    voice_id: str,
    emotion: str | None,
    mode: str,
) -> None:
    """Split text into sentences and send TTS audio bytes over the WebSocket."""
    if mode != "text" and text.strip():
        for sentence in split_sentences(text):
            audio = await client.synthesize(sentence, voice_id=voice_id, emotion=emotion)
            if audio:
                await websocket.send_bytes(audio)


async def _process_image_message(
    websocket: WebSocket,
    client: ServiceClient,
    user_text: str,
    image_data: str,
    conversation_id: str | None,
    provider: str,
    model: str | None,
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
        model=model,
    ):
        if event.get("type") == "token":
            content = event.get("content", "")
            full_text += content
            await websocket.send_json({"type": "response.text", "content": content})
        elif event.get("type") == "done":
            full_text = event.get("content", full_text)
        elif event.get("type") == "error":
            await websocket.send_json(
                {"type": "error", "code": "brain_error", "message": event.get("error", "Unknown error")}
            )
            return

    await _synthesize_and_send(websocket, client, full_text, voice_id, None, mode)
    await websocket.send_json({"type": "response.end", "full_text": full_text})


async def _process_and_respond(
    websocket: WebSocket,
    client: ServiceClient,
    user_text: str,
    conversation_id: str | None,
    provider: str,
    model: str | None,
    voice_id: str,
    mode: str,
) -> None:
    """Send user text to brain, stream response text, and optionally TTS audio."""
    try:
        intent_name, tool_filter, confidence = classify_intent(user_text)
    except Exception:
        intent_name, tool_filter, confidence = None, None, 0.0

    log.info("intent_dispatch", message=user_text[:80], intent=intent_name, confidence=round(confidence, 3))

    if intent_name == "generate_image":
        await websocket.send_json({"type": "response.text", "content": "Generating your image..."})
        image_bytes = await client.generate_image(user_text, width=512, height=512)
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode()
            await websocket.send_json(
                {"type": "response.image", "image_data": f"data:image/png;base64,{image_b64}", "prompt": user_text}
            )
        else:
            await websocket.send_json({"type": "response.text", "content": "I wasn't able to generate the image."})
        await websocket.send_json({"type": "response.end", "full_text": ""})
        return

    async def on_tool_result(name: str, args: dict, result: str):
        if name == "web_browse_search":
            try:
                raw_data = json.loads(result)
                results = raw_data.get("results") if isinstance(raw_data, dict) else raw_data
                await websocket.send_json(
                    {"type": "response.web_results", "results": results, "query": args.get("query")}
                )
            except Exception:
                pass
        elif name == "web_browse_fetch":
            await websocket.send_json({"type": "response.web_results", "page_content": result, "url": args.get("url")})
        elif name == "weather_get":
            try:
                weather_data = json.loads(result)
                await websocket.send_json(
                    {
                        "type": "response.web_results",
                        "results": [
                            {
                                "title": f"Weather for {weather_data.get('location')}",
                                "snippet": weather_data.get("text"),
                                "url": "https://www.bom.gov.au"
                                if "Meteorology" in weather_data.get("source", "")
                                else "https://openweathermap.org",
                            }
                        ],
                        "query": f"Weather in {args.get('location')}",
                    }
                )
            except Exception:
                pass

    require_token = intent_name not in _NO_TOKEN_INTENTS

    if tool_filter:
        result = await run_tool_loop(
            client=client,
            initial_message=user_text,
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            tool_filter=tool_filter,
            on_tool_result=on_tool_result,
            require_token=require_token,
            intent=intent_name,
        )

        if result.get("session_expired"):
            await websocket.send_json({"type": "error", "code": "session_expired", "message": result.get("message")})
            return

        emotion, full_text = _sanitize_response(result.get("message", ""))
        if emotion:
            await websocket.send_json({"type": "response.emotion", "emotion": emotion})

        if full_text:
            await websocket.send_json({"type": "response.text", "content": full_text})

        await _synthesize_and_send(websocket, client, full_text, voice_id, emotion, mode)
        await websocket.send_json({"type": "response.end", "full_text": full_text})
        return

    # No tools path - buffer response to ensure no technical tags are leaked
    full_text = ""
    async for event in client.chat_stream(
        message=user_text, conversation_id=conversation_id, provider=provider, model=model
    ):
        if event.get("type") == "token":
            full_text += event.get("content", "")
        elif event.get("type") == "done":
            full_text = event.get("content", full_text)
        elif event.get("type") == "error":
            await websocket.send_json({"type": "error", "code": "brain_error", "message": event.get("error")})
            return

    emotion, full_text = _sanitize_response(full_text)
    if emotion:
        await websocket.send_json({"type": "response.emotion", "emotion": emotion})
    if full_text:
        await websocket.send_json({"type": "response.text", "content": full_text})

    await _synthesize_and_send(websocket, client, full_text, voice_id, emotion, mode)
    await websocket.send_json({"type": "response.end", "full_text": full_text})
