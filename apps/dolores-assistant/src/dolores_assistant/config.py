"""Configuration for dolores-assistant orchestrator."""

from __future__ import annotations

import json

from dolores_common.config import get_env, get_env_int


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
    default_model: str = get_env("DEFAULT_MODEL", "llama3.2")

    # Logging
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")

    # Image generation service
    imagen_url: str = get_env("DOLORES_IMAGEN_URL", "http://localhost:8005")
    imagen_timeout: int = get_env_int("IMAGEN_TIMEOUT", 300)

    # Long-term memory
    memory_db_path: str = get_env("MEMORY_DB_PATH", "data/memory.db")

    # Weather
    owm_api_key: str = get_env("OPENWEATHERMAP_API_KEY", "")

    # Integrations — JSON array of {name, url, spec_path?, auth?}
    # Example: [{"name":"todo","url":"http://todo:5000","spec_path":"/api/openapi.json"}]
    @property
    def integrations(self) -> list[dict]:
        raw = get_env("DOLORES_INTEGRATIONS", "")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []


settings = AssistantConfig()
