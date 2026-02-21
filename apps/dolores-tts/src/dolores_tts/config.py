"""Configuration for dolores-tts service."""

from __future__ import annotations

from dolores_common.config import get_env, get_env_int


class TTSConfig:
    """TTS service configuration from environment variables."""

    engine: str = get_env("TTS_ENGINE", "coqui_xtts")  # coqui_xtts or piper
    device: str = get_env("TTS_DEVICE", "auto")
    voices_dir: str = get_env("TTS_VOICES_DIR", "data/voices")
    db_path: str = get_env("TTS_DB_PATH", "data/tts.db")
    sample_rate: int = get_env_int("TTS_SAMPLE_RATE", 24000)
    max_text_length: int = get_env_int("TTS_MAX_TEXT_LENGTH", 5000)

    # Logging
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")


settings = TTSConfig()
