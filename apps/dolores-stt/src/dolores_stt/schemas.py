"""Request/response schemas for the STT service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    text: str
    segments: list[SegmentOut] = []
    language: str
    language_probability: float
    duration_seconds: float
    processing_time_ms: int


class SegmentOut(BaseModel):
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


# Rebuild TranscribeResponse now that SegmentOut is defined
TranscribeResponse.model_rebuild()


class StreamMessage(BaseModel):
    """WebSocket message for streaming transcription."""

    type: str = Field(..., pattern="^(partial|final|error)$")
    text: str = ""
    language: str = ""
    error: str = ""


class IdentifyResponse(BaseModel):
    """Response from /v1/identify endpoint."""

    speaker_id: str | None = None
    speaker_name: str | None = None
    confidence: float = 0.0


class SpeakerProfile(BaseModel):
    """Speaker profile for list/get/enroll responses."""

    id: str | None = None
    name: str
    email: str | None = None
    samples_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
