"""Request/response schemas for the TTS service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EmotionType = Literal["happy", "sad", "angry", "neutral"]


class SynthesizeRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    voice_id: str = "default"
    output_format: str = "wav"  # wav or opus (future)
    sample_rate: int = 24000
    emotion: EmotionType | None = None


class VoiceProfile(BaseModel):
    id: str
    name: str
    description: str = ""
    engine: str  # coqui_xtts, piper, or f5_tts
    ref_text: str | None = None
    created_at: str


class VoiceCreateResponse(BaseModel):
    id: str
    name: str
    engine: str
    ref_text: str | None = None
