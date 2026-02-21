"""STT API routes: POST /v1/transcribe, WS /v1/stream."""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from dolores_common.auth import ServicePSK
from dolores_common.logging import get_logger

from .config import settings
from .engine import SUPPORTED_FORMATS, STTEngine
from .schemas import StreamMessage, TranscribeResponse

log = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["stt"])

# Singleton engine — initialized at app startup via lifespan
_engine: STTEngine | None = None


def get_engine() -> STTEngine:
    if _engine is None or not _engine.is_loaded:
        raise HTTPException(status_code=503, detail="STT model not loaded yet")
    return _engine


def set_engine(engine: STTEngine) -> None:
    global _engine
    _engine = engine


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile,
    language: str | None = None,
    _auth: ServicePSK = None,
    engine: STTEngine = Depends(get_engine),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file."""
    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format: {content_type}. Supported: {', '.join(SUPPORTED_FORMATS)}",
        )

    # Read and validate size
    audio_data = await file.read()
    if len(audio_data) > settings.max_upload_bytes:
        max_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File too large. Maximum: {max_mb} MB")

    if len(audio_data) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    log.info("transcribe_request", content_type=content_type, size_bytes=len(audio_data))

    result = engine.transcribe(audio_data, content_type=content_type, language=language)
    return TranscribeResponse(**result)


@router.websocket("/stream")
async def stream_transcription(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming transcription.

    Protocol:
    - Client sends binary audio chunks
    - Client sends JSON {"type": "audio.end"} when done
    - Server sends JSON StreamMessage (partial/final)
    """
    await websocket.accept()
    engine = _engine

    if engine is None or not engine.is_loaded:
        await websocket.send_json({"type": "error", "text": "", "error": "STT model not loaded"})
        await websocket.close(code=1011)
        return

    audio_buffer = io.BytesIO()

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                audio_buffer.write(message["bytes"])

            elif "text" in message:
                import json

                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {"type": "error", "text": "", "error": "Invalid JSON"}
                    )
                    continue

                if data.get("type") == "audio.end":
                    # Process accumulated audio
                    audio_data = audio_buffer.getvalue()
                    if not audio_data:
                        await websocket.send_json(
                            {"type": "error", "text": "", "error": "No audio data received"}
                        )
                        audio_buffer = io.BytesIO()
                        continue

                    language = data.get("language")

                    for chunk in engine.transcribe_stream(
                        audio_data, content_type="audio/webm", language=language
                    ):
                        await websocket.send_json(
                            StreamMessage(
                                type=chunk["type"],
                                text=chunk["text"],
                                language=chunk.get("language", ""),
                            ).model_dump()
                        )

                    # Reset buffer for next utterance
                    audio_buffer = io.BytesIO()

    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception as e:
        log.error("ws_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "text": "", "error": str(e)})
        except Exception:
            pass
