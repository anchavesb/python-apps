"""Assistant API routes: WS /v1/conversation, POST /v1/chat."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from dolores_common.auth import ClientAPIKey, validate_ws_token
from dolores_common.logging import get_logger

from .config import settings
from .pipeline import ServiceClient, run_tool_loop, split_sentences
from .schemas import TextChatRequest, TextChatResponse

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
    _auth: ClientAPIKey = None,
    client: ServiceClient = Depends(get_service_client),
) -> TextChatResponse:
    """Text-only chat endpoint (simpler alternative to WebSocket)."""
    result = await run_tool_loop(
        client=client,
        initial_message=req.message,
        conversation_id=req.conversation_id,
        provider=req.provider,
    )

    return TextChatResponse(
        message=result.get("message", ""),
        conversation_id=result.get("conversation_id", ""),
    )


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
        conversation_id = msg.get("conversation_id")

        await websocket.send_json({
            "type": "session.created",
            "session_id": session_id,
            "conversation_id": conversation_id or "",
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
                if not audio_buffer:
                    await websocket.send_json({"type": "error", "code": "no_audio", "message": "No audio data received"})
                    continue

                # STT
                transcription = await client.transcribe(bytes(audio_buffer))
                audio_buffer = bytearray()

                if transcription is None:
                    await websocket.send_json({
                        "type": "error",
                        "code": "stt_unavailable",
                        "message": "Speech recognition failed, please type instead",
                    })
                    continue

                user_text = transcription.get("text", "")
                await websocket.send_json({"type": "transcription.final", "text": user_text})

                if not user_text.strip():
                    continue

                # Brain -> response
                await _process_and_respond(
                    websocket, client, user_text, conversation_id, provider, voice_id, mode
                )

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
    full_text = ""

    async for event in client.chat_stream(
        message=user_text,
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
            await websocket.send_json({
                "type": "error",
                "code": "brain_error",
                "message": event.get("error", "Unknown error"),
            })
            return

    # TTS: synthesize sentences and send audio
    if mode != "text" and full_text.strip():
        sentences = split_sentences(full_text)
        for sentence in sentences:
            audio = await client.synthesize(sentence, voice_id=voice_id)
            if audio:
                await websocket.send_bytes(audio)

    await websocket.send_json({"type": "response.end", "full_text": full_text})
