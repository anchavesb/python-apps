"""Configuration for dolores-brain service."""

from __future__ import annotations

from dolores_common.config import get_env, get_env_int


class BrainConfig:
    """Brain service configuration from environment variables."""

    default_provider: str = get_env("DEFAULT_PROVIDER", "ollama")
    default_model: str = get_env("DEFAULT_MODEL", "llama3.2")

    # Ollama
    ollama_base_url: str = get_env("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = get_env("OLLAMA_MODEL", "llama3.2")

    # Cloud providers (optional)
    anthropic_api_key: str = get_env("ANTHROPIC_API_KEY", "")
    openai_api_key: str = get_env("OPENAI_API_KEY", "")

    # Defaults
    max_tokens: int = get_env_int("DEFAULT_MAX_TOKENS", 1024)
    temperature: float = float(get_env("DEFAULT_TEMPERATURE", "0.7"))

    # SQLite for conversations
    db_path: str = get_env("BRAIN_DB_PATH", "data/conversations.db")

    # Logging
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")


settings = BrainConfig()
