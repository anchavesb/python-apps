"""STT API routes: POST /v1/transcribe, WS /v1/stream, speaker identification."""

from __future__ import annotations

import asyncio
import io
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from dolores_common.auth import ServicePSK
from dolores_common.logging import get_logger

from .config import settings
from .engine import SUPPORTED_FORMATS, STTEngine
from .schemas import (
    IdentifyResponse,
    SpeakerProfile,
    StreamMessage,
    TranscribeResponse,
)
from .speaker import SpeakerIdentifier

log = get_logger(__name__)

# Max size per audio file for enrollment (10 MB)
_MAX_ENROLL_FILE_BYTES = 10 * 1024 * 1024


def _validate_uuid(value: str, label: str = "ID") -> None:
    """Validate that a string is a valid UUID4."""
    try:
        _uuid.UUID(value, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {value}")

router = APIRouter(prefix="/v1", tags=["stt"])

# Singleton engine — initialized at app startup via lifespan
_engine: STTEngine | None = None
_speaker_identifier: SpeakerIdentifier | None = None


def get_engine() -> STTEngine:
    if _engine is None or not _engine.is_loaded:
        raise HTTPException(status_code=503, detail="STT model not loaded yet")
    return _engine


def set_engine(engine: STTEngine) -> None:
    global _engine
    _engine = engine


def set_speaker_identifier(identifier: SpeakerIdentifier) -> None:
    global _speaker_identifier
    _speaker_identifier = identifier


def get_speaker_identifier() -> SpeakerIdentifier:
    if _speaker_identifier is None:
        raise HTTPException(status_code=503, detail="Speaker identification not enabled")
    return _speaker_identifier


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile,
    language: str | None = None,
    _auth: ServicePSK = None,
    engine: STTEngine = Depends(get_engine),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file."""
    # Validate content type (strip codec params like ";codecs=opus")
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip()
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


# --- Speaker identification ---


@router.post("/identify", response_model=IdentifyResponse)
async def identify_speaker(
    file: UploadFile,
    _auth: ServicePSK = None,
    identifier: SpeakerIdentifier = Depends(get_speaker_identifier),
) -> IdentifyResponse:
    """Identify the speaker from an audio file."""
    audio_data = await file.read()
    if len(audio_data) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    content_type = (file.content_type or "audio/webm").split(";")[0].strip()
    log.info("identify_request", content_type=content_type, size_bytes=len(audio_data))

    result = await asyncio.to_thread(identifier.identify, audio_data, content_type)
    return IdentifyResponse(**result)


@router.post("/speakers", response_model=SpeakerProfile)
async def enroll_speaker(
    name: str,
    files: list[UploadFile],
    email: str | None = None,
    _auth: ServicePSK = None,
    identifier: SpeakerIdentifier = Depends(get_speaker_identifier),
) -> SpeakerProfile:
    """Enroll a new speaker from one or more audio files."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    audio_samples = []
    for f in files:
        data = await f.read()
        if len(data) > _MAX_ENROLL_FILE_BYTES:
            max_mb = _MAX_ENROLL_FILE_BYTES // (1024 * 1024)
            raise HTTPException(status_code=413, detail=f"Audio file too large. Maximum: {max_mb} MB")
        if data:
            ct = (f.content_type or "audio/webm").split(";")[0].strip()
            audio_samples.append((data, ct))

    if not audio_samples:
        raise HTTPException(status_code=400, detail="No valid audio data provided")

    try:
        result = await asyncio.to_thread(
            identifier.enroll, name, audio_samples, email
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SpeakerProfile(**result)


@router.get("/speakers", response_model=list[SpeakerProfile])
async def list_speakers(
    _auth: ServicePSK = None,
    identifier: SpeakerIdentifier = Depends(get_speaker_identifier),
) -> list[SpeakerProfile]:
    """List all enrolled speaker profiles."""
    return identifier.store.list_speakers()


@router.get("/speakers/{speaker_id}", response_model=SpeakerProfile)
async def get_speaker(
    speaker_id: str,
    _auth: ServicePSK = None,
    identifier: SpeakerIdentifier = Depends(get_speaker_identifier),
) -> SpeakerProfile:
    """Get a speaker profile by ID."""
    _validate_uuid(speaker_id, "speaker_id")
    profile = identifier.store.get(speaker_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return SpeakerProfile(**profile)


@router.delete("/speakers/{speaker_id}", status_code=204)
async def delete_speaker(
    speaker_id: str,
    _auth: ServicePSK = None,
    identifier: SpeakerIdentifier = Depends(get_speaker_identifier),
) -> None:
    """Delete a speaker profile."""
    _validate_uuid(speaker_id, "speaker_id")
    if not identifier.store.delete(speaker_id):
        raise HTTPException(status_code=404, detail="Speaker not found")


# --- WebSocket streaming ---


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
