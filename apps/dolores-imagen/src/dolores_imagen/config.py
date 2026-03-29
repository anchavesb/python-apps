"""Configuration for dolores-imagen service."""

from __future__ import annotations

from dolores_common.config import get_env, get_env_int


class ImagegenConfig:
    """Image generation service configuration from environment variables."""

    provider: str = get_env("IMAGEN_PROVIDER", "flux")
    flux_model_id: str = get_env("FLUX_MODEL_ID", "black-forest-labs/FLUX.1-schnell")
    sd_model_id: str = get_env("SD_MODEL_ID", "runwayml/stable-diffusion-v-1-5")
    generation_timeout: int = get_env_int("GENERATION_TIMEOUT", 300)
    port: int = get_env_int("PORT", 8005)
    log_level: str = get_env("LOG_LEVEL", "INFO")
    log_format: str = get_env("LOG_FORMAT", "console")


settings = ImagegenConfig()
