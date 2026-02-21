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
