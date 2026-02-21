"""Configuration for dolores-cli."""

from __future__ import annotations

import os


class CLIConfig:
    """CLI configuration from environment variables."""

    server_url: str = os.environ.get("DOLORES_SERVER_URL", "ws://localhost:8000")
    api_key: str = os.environ.get("DOLORES_API_KEY", "")
    provider: str = os.environ.get("DOLORES_PROVIDER", "")
    voice_id: str = os.environ.get("DOLORES_VOICE_ID", "default")


settings = CLIConfig()
