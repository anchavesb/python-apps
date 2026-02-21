"""Request/response schemas for the Brain service."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tools: list[dict] | None = None
    max_tokens: int = 1024
    temperature: float = 0.7


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    provider: str
    model: str
    usage: dict | None = None
    tool_calls: list[dict] = []
    processing_time_ms: int


class ProviderInfo(BaseModel):
    name: str
    models: list[str]
    default_model: str
