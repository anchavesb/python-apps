"""Request/response schemas for the TTS service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    voice_id: str = "default"
    output_format: str = "wav"  # wav or opus (future)
    sample_rate: int = 24000


class VoiceProfile(BaseModel):
    id: str
    name: str
    description: str = ""
    engine: str  # coqui_xtts or piper
    created_at: str


class VoiceCreateResponse(BaseModel):
    id: str
    name: str
    engine: str
