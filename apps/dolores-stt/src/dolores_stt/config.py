"""Configuration for dolores-stt service."""

from __future__ import annotations

from dolores_common.config import get_env, get_env_int


class STTConfig:
    """STT service configuration from environment variables."""

    model_size: str = get_env("STT_MODEL_SIZE", "large-v3-turbo")
    device: str = get_env("STT_DEVICE", "auto")
    compute_type: str = get_env("STT_COMPUTE_TYPE", "int8")
    cpu_threads: int = get_env_int("STT_CPU_THREADS", 4)
    max_upload_bytes: int = get_env_int("STT_MAX_UPLOAD_MB", 25) * 1024 * 1024
    beam_size: int = get_env_int("STT_BEAM_SIZE", 5)
    language: str = get_env("STT_LANGUAGE", "")  # empty = auto-detect
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")


settings = STTConfig()
