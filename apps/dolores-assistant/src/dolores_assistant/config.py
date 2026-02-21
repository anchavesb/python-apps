"""Configuration for dolores-assistant orchestrator."""

from __future__ import annotations

from dolores_common.config import get_env, get_env_int, get_env_bool


class AssistantConfig:
    """Assistant orchestrator configuration from environment variables."""

    # Service URLs
    stt_url: str = get_env("DOLORES_STT_URL", "http://localhost:8001")
    tts_url: str = get_env("DOLORES_TTS_URL", "http://localhost:8002")
    brain_url: str = get_env("DOLORES_BRAIN_URL", "http://localhost:8003")

    # Timeouts (seconds)
    stt_timeout: int = get_env_int("STT_TIMEOUT", 30)
    tts_timeout: int = get_env_int("TTS_TIMEOUT", 30)
    brain_timeout: int = get_env_int("BRAIN_TIMEOUT", 60)

    # WebSocket
    max_session_seconds: int = get_env_int("MAX_SESSION_SECONDS", 300)

    # Defaults
    default_voice_id: str = get_env("DEFAULT_VOICE_ID", "default")
    default_provider: str = get_env("DEFAULT_PROVIDER", "ollama")

    # Logging
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")


settings = AssistantConfig()
