"""Request/response schemas for the Assistant orchestrator."""

from __future__ import annotations

from pydantic import BaseModel


class TextChatRequest(BaseModel):
    """POST /v1/chat request body."""
    message: str
    conversation_id: str | None = None
    provider: str | None = None
    tts: bool = False
    voice_id: str = "default"


class TextChatResponse(BaseModel):
    """POST /v1/chat response body."""
    message: str
    conversation_id: str


# WebSocket protocol message types
class WSSessionStart(BaseModel):
    type: str = "session.start"
    voice_id: str = "default"
    provider: str | None = None
    mode: str = "both"  # voice, text, or both
    token: str | None = None
    conversation_id: str | None = None


class WSSessionCreated(BaseModel):
    type: str = "session.created"
    session_id: str
    conversation_id: str
