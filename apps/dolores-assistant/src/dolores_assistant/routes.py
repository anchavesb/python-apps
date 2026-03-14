"""Assistant API routes: WS /v1/conversation, POST /v1/chat, voice & speaker management."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from dolores_common.auth import ClientAPIKey, validate_ws_token
from dolores_common.logging import get_logger

from .config import settings
from .pipeline import ServiceClient, run_tool_loop, split_sentences
from .schemas import TextChatRequest, TextChatResponse
from .tools.openapi_discovery import current_user_token
from .tools.registry import get_tool_definitions

SPEAKER_NAME_RE = re.compile(r"^[a-zA-Z0-9 ]{1,32}$")

log = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["assistant"])

_service_client: ServiceClient | None = None


def get_service_client() -> ServiceClient:
    if _service_client is None:
        raise HTTPException(status_code=503, detail="Service client not initialized")
    return _service_client


def set_service_client(client: ServiceClient) -> None:
    global _service_client
    _service_client = client


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
    success = await client.delete_speaker(speaker_id)
    if not success:
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

        await websocket.send_json({
            "type": "session.created",
            "session_id": session_id,
            "conversation_id": conversation_id,
        })

        log.info("session_started", session_id=session_id, mode=mode, provider=provider)

        # Main message loop
        while True:
            message = await websocket.receive()

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
                    await websocket.send_json({"type": "error", "code": "no_audio", "message": "No audio data received"})
                    continue

                # Validate audio magic bytes
                valid = False
                if len(audio_data) >= 4:
                    header = audio_data[:4]
                    # WebM/MKV (EBML): 0x1A45DFA3
                    if header == b'\x1a\x45\xdf\xa3':
                        valid = True
                    # MP4/M4A (ftyp): bytes 4-7 are 'ftyp' but byte 0-3 is box size
                    elif len(audio_data) >= 8 and audio_data[4:8] == b'ftyp':
                        valid = True
                    # OGG: 'OggS'
                    elif header == b'OggS':
                        valid = True

                if not valid:
                    log.warning("unrecognized_audio_header", size=len(audio_data), header=audio_data[:8].hex() if len(audio_data) >= 8 else audio_data.hex(), content_type=content_type)
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
                    await websocket.send_json({
                        "type": "error",
                        "code": "stt_unavailable",
                        "message": "Speech recognition failed, please type instead",
                    })
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
                brain_text = user_text
                if speaker_result and speaker_result.get("speaker_name"):
                    name = speaker_result["speaker_name"]
                    confidence = speaker_result.get("confidence", 0)
                    if confidence >= 0.85 and SPEAKER_NAME_RE.match(name):
                        brain_text = f"[Speaker: {name}] {user_text}"

                # Brain -> response
                await _process_and_respond(
                    websocket, client, brain_text, conversation_id, provider, voice_id, mode
                )

            elif msg_type == "session.update_token":
                new_token = data.get("user_token")
                _cv_token = current_user_token.set(new_token)
                log.info("token_updated", session_id=session_id)
                continue

            elif msg_type == "text.send":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                await _process_and_respond(
                    websocket, client, user_text, conversation_id, provider, voice_id, mode
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
_VALID_EMOTIONS = {"neutral", "curious", "happy", "sad", "surprised", "empathetic"}

def _detect_tool_filter(message: str) -> set[str] | None:
    """Classify message intent and return tool name filter, or None for chat."""
    from .intent import classify_intent
    _, tool_filter, _ = classify_intent(message)
    return tool_filter


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

    # Only use tool loop when: user has JWT AND message matches a tool intent.
    # Filter tools to the relevant subset so the LLM doesn't get confused.
    has_user_token = current_user_token.get() is not None
    tool_filter = _detect_tool_filter(user_text) if has_user_token else None
    if tool_filter and get_tool_definitions(tool_filter):
        result = await run_tool_loop(
            client=client,
            initial_message=user_text,
            conversation_id=conversation_id,
            provider=provider,
            tool_filter=tool_filter,
        )

        # Handle session expiry with a dedicated event so the UI can prompt re-login
        if result.get("session_expired"):
            await websocket.send_json({
                "type": "error",
                "code": "session_expired",
                "message": result.get("message", "Your session has expired."),
            })
            return

        full_text = result.get("message", "")

        # Parse and strip emotion tag
        m = _EMOTION_TAG_RE.match(full_text)
        if m:
            emotion = m.group(1)
            if emotion in _VALID_EMOTIONS:
                await websocket.send_json({"type": "response.emotion", "emotion": emotion})
            full_text = full_text[m.end():]

        if full_text:
            await websocket.send_json({"type": "response.text", "content": full_text})

        # TTS
        if mode != "text" and full_text.strip():
            sentences = split_sentences(full_text)
            for sentence in sentences:
                audio = await client.synthesize(sentence, voice_id=voice_id)
                if audio:
                    await websocket.send_bytes(audio)

        await websocket.send_json({"type": "response.end", "full_text": full_text})
        return

    # No tools — use streaming path for faster response
    full_text = ""
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
                    emotion = match.group(1)
                    if emotion in _VALID_EMOTIONS:
                        await websocket.send_json({"type": "response.emotion", "emotion": emotion})
                    # Strip the tag and send the remainder
                    remainder = emotion_buffer[match.end():]
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
                full_text = full_text[m.end():]

        elif event.get("type") == "error":
            await websocket.send_json({
                "type": "error",
                "code": "brain_error",
                "message": event.get("error", "Unknown error"),
            })
            return

    # Flush any remaining buffer (short responses)
    if not emotion_parsed and emotion_buffer:
        match = _EMOTION_TAG_RE.match(emotion_buffer)
        if match:
            emotion = match.group(1)
            if emotion in _VALID_EMOTIONS:
                await websocket.send_json({"type": "response.emotion", "emotion": emotion})
            remainder = emotion_buffer[match.end():]
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
            audio = await client.synthesize(sentence, voice_id=voice_id)
            if audio:
                await websocket.send_bytes(audio)

    await websocket.send_json({"type": "response.end", "full_text": full_text})
