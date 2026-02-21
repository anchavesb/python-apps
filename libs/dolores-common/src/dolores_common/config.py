"""Base configuration utilities for Dolores services."""

from __future__ import annotations

import os


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.environ.get(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """Get environment variable as integer."""
    return int(os.environ.get(key, str(default)))


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean."""
    val = os.environ.get(key, str(default)).lower()
    return val in ("true", "1", "yes")
