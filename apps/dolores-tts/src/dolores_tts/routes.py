"""TTS API routes: POST /v1/synthesize, GET/POST /v1/voices."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from dolores_common.auth import ServicePSK
from dolores_common.logging import get_logger

from .config import settings
from .engine import TTSEngine
from .schemas import SynthesizeRequest, VoiceCreateResponse, VoiceProfile
from .voice_profiles import VoiceProfileStore

log = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["tts"])

_engine: TTSEngine | None = None
_voice_store: VoiceProfileStore | None = None


def get_engine() -> TTSEngine:
    if _engine is None or not _engine.is_loaded:
        raise HTTPException(status_code=503, detail="TTS model not loaded yet")
    return _engine


def get_voice_store() -> VoiceProfileStore:
    if _voice_store is None:
        raise HTTPException(status_code=503, detail="Voice profile store not initialized")
    return _voice_store


def set_engine(engine: TTSEngine) -> None:
    global _engine
    _engine = engine


def set_voice_store(store: VoiceProfileStore) -> None:
    global _voice_store
    _voice_store = store


@router.post("/synthesize")
async def synthesize(
    req: SynthesizeRequest,
    _auth: ServicePSK = None,
    engine: TTSEngine = Depends(get_engine),
) -> Response:
    """Synthesize text to audio. Returns WAV binary."""
    if len(req.text) > settings.max_text_length:
        raise HTTPException(status_code=400, detail=f"Text too long. Maximum: {settings.max_text_length} chars")

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    log.info("synthesize_request", voice_id=req.voice_id, text_length=len(req.text))

    wav_bytes = engine.synthesize(
        text=req.text,
        voice_id=req.voice_id,
        sample_rate=req.sample_rate,
    )

    return Response(content=wav_bytes, media_type="audio/wav")


@router.get("/voices", response_model=list[VoiceProfile])
async def list_voices(
    _auth: ServicePSK = None,
    store: VoiceProfileStore = Depends(get_voice_store),
) -> list[VoiceProfile]:
    """List available voice profiles."""
    profiles = await store.list_profiles()
    return [VoiceProfile(**p) for p in profiles]


@router.post("/voices", response_model=VoiceCreateResponse)
async def create_voice(
    name: str,
    file: UploadFile,
    description: str = "",
    _auth: ServicePSK = None,
    store: VoiceProfileStore = Depends(get_voice_store),
) -> VoiceCreateResponse:
    """Create a new voice profile from reference audio."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="File must be an audio file")

    audio_data = await file.read()
    if len(audio_data) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # Max 10 MB for reference audio
    if len(audio_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Reference audio too large. Maximum: 10 MB")

    result = await store.create(
        name=name,
        audio_data=audio_data,
        engine=_engine.name if _engine else "coqui_xtts",
        description=description,
    )
    return VoiceCreateResponse(**result)
