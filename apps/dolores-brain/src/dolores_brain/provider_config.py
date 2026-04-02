"""Provider-specific configuration for LiteLLM.

This module configures LiteLLM's environment so it can route to the
correct providers. No custom provider abstraction — LiteLLM handles that.
"""

from __future__ import annotations

import os

from dolores_common.logging import get_logger

from .config import settings

log = get_logger(__name__)

PROVIDERS: dict[str, dict] = {}


def setup_providers() -> dict[str, dict]:
    """Configure LiteLLM environment variables and return available providers."""
    # Clear and update in-place so references from other modules stay valid
    PROVIDERS.clear()

    # Ollama (local)
    if settings.ollama_base_url:
        os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url
        # Use default_model if provider is ollama, otherwise fallback to llama3.2
        model = settings.ollama_model
        if settings.default_provider == "ollama":
            model = settings.default_model

        PROVIDERS["ollama"] = {
            "name": "ollama",
            "prefix": "ollama/",
            "models": [model],
            "default_model": model,
        }
        log.info("provider_configured", provider="ollama", base_url=settings.ollama_base_url, model=model)

    # Anthropic (Claude)
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        PROVIDERS["anthropic"] = {
            "name": "anthropic",
            "prefix": "",
            "models": ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"],
            "default_model": "claude-sonnet-4-20250514",
        }
        log.info("provider_configured", provider="anthropic")

    # OpenAI
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        PROVIDERS["openai"] = {
            "name": "openai",
            "prefix": "",
            "models": ["gpt-4o", "gpt-4o-mini"],
            "default_model": "gpt-4o",
        }
        log.info("provider_configured", provider="openai")

    return PROVIDERS


def resolve_model(provider: str | None, model: str | None, vision_provider: str | None = None) -> str:
    """Resolve the LiteLLM model string from provider/model inputs.

    When vision_provider is given and non-empty it overrides provider for model resolution.
    Returns the model string LiteLLM expects (e.g. "ollama/llama3.2", "claude-sonnet-4-20250514").
    """
    is_vision = vision_provider is not None
    provider = (vision_provider if vision_provider else None) or provider or settings.default_provider
    prov_info = PROVIDERS.get(provider)

    if not prov_info:
        raise ValueError(f"Provider '{provider}' not available. Available: {list(PROVIDERS.keys())}")

    # Use vision_model override if this is a vision request and it's set
    if is_vision and settings.vision_model:
        model = settings.vision_model
    else:
        model = model or prov_info["default_model"]

    prefix = prov_info["prefix"]

    # Add prefix if needed (ollama requires "ollama/" prefix for LiteLLM)
    if prefix and not model.startswith(prefix):
        return f"{prefix}{model}"
    return model
