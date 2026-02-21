"""Shared Pydantic models used across Dolores services."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


class TranscriptionResult(BaseModel):
    text: str
    segments: list[TranscriptionSegment] = []
    language: str = "en"
    duration_seconds: float
    processing_time_ms: int


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tools: list[str] = []
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False
    tts: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    provider: str
    model: str
    usage: dict | None = None
    tool_calls: list[dict] = []
    processing_time_ms: int


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class HealthStatus(BaseModel):
    status: str = "ok"
    service: str
    version: str
    uptime_seconds: float
    details: dict = {}
