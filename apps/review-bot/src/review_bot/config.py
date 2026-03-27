"""Configuration for review-bot service.

Exposes:
  - ReviewBotConfig: service settings read from environment variables
  - RepoEntry / RepoRegistry: YAML registry models
  - EffectiveConfig: resolved per-repo configuration passed to review pipeline
  - load_registry / get_registry / get_settings: module-level singletons
  - resolve_effective_config / merge_per_repo_config: precedence resolution
"""

from __future__ import annotations

import os
from typing import Any

import yaml
from pydantic import BaseModel

from dolores_common.config import get_env, get_env_int
from dolores_common.logging import get_logger

log = get_logger(__name__)


class RegistryError(Exception):
    """Raised when a repo is not registered in repos.yml."""


class EffectiveConfig(BaseModel):
    """Resolved, per-repo configuration used throughout the review pipeline."""

    repo: str
    model: str
    prompt_mode: str
    prompt_extension: str | None
    api_key: str
    github_token: str


class ReviewBotConfig:
    """Review bot service configuration from environment variables."""

    def __init__(self) -> None:
        self.poll_interval_seconds: int = get_env_int("REVIEW_BOT_POLL_INTERVAL_SECONDS", 60)
        self.state_db_path: str = get_env("REVIEW_BOT_STATE_DB_PATH", "data/state.db")
        self.registry_path: str = get_env("REVIEW_BOT_REGISTRY_PATH", "config/repos.yml")
        self.prompts_dir: str = get_env("REVIEW_BOT_PROMPTS_DIR", "prompts")
        self.max_concurrent_reviews: int = get_env_int("REVIEW_BOT_MAX_CONCURRENT", 3)
        self.log_level: str = get_env("REVIEW_BOT_LOG_LEVEL", "INFO")
        self.log_format: str = get_env("REVIEW_BOT_LOG_FORMAT", "json")


class RepoEntry(BaseModel):
    """A single repository entry in repos.yml."""

    repo: str
    model: str | None = None


class _Defaults(BaseModel):
    model: str


class RepoRegistry(BaseModel):
    """Top-level repos.yml structure."""

    defaults: _Defaults
    repositories: list[RepoEntry]


_registry: RepoRegistry | None = None
_settings: ReviewBotConfig | None = None


def load_registry(path: str) -> None:
    """Read repos.yml from *path* and store in the module-level singleton."""
    global _registry
    with open(path) as fh:
        data = yaml.safe_load(fh)
    _registry = RepoRegistry(**data)


def get_registry() -> RepoRegistry:
    """Return the loaded registry; raises RuntimeError if not yet loaded."""
    if _registry is None:
        raise RuntimeError("Registry not loaded — call load_registry() first")
    return _registry


def get_settings() -> ReviewBotConfig:
    """Return the module-level settings singleton."""
    global _settings
    if _settings is None:
        _settings = ReviewBotConfig()
    return _settings


def _safe_name(repo: str) -> str:
    """Derive the env-var safe name fragment from an 'owner/repo' string.

    Example: 'anchavesb/my-app' → 'ANCHAVESB_MY_APP'
    """
    return repo.upper().replace("/", "_").replace("-", "_")


def _resolve_api_key(model: str, repo: str) -> str:
    """Return the best available API key for *model* + *repo*.

    Precedence: per-repo env override > shared global key.
    """
    safe = _safe_name(repo)
    if model.startswith("gemini/"):
        return os.environ.get(f"REPO_{safe}_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if model.startswith("anthropic/"):
        return os.environ.get(f"REPO_{safe}_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    return ""


def _resolve_github_token(repo: str) -> str:
    """Return the GitHub token for *repo*, with per-repo override support."""
    safe = _safe_name(repo)
    return os.environ.get(f"REPO_{safe}_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")


def resolve_effective_config(
    repo: str,
    per_repo_yml_content: str | None = None,
) -> EffectiveConfig:
    """Resolve final configuration for *repo* with three-level precedence.

    Precedence (highest → lowest):
      1. Per-repo ``review-bot.yml`` content (already fetched by caller)
      2. Per-repo entry in the central ``repos.yml`` registry
      3. Global ``defaults`` in ``repos.yml``

    Raises:
        RegistryError: when *repo* is absent from the registry.
    """
    registry = get_registry()

    entry = next((r for r in registry.repositories if r.repo == repo), None)
    if entry is None:
        raise RegistryError(
            f"Repository '{repo}' is not registered in repos.yml. "
            "Add it to the repositories list to enable automated reviews."
        )

    # Layer 3 — global defaults
    model: str = registry.defaults.model
    prompt_mode: str = "base"
    prompt_extension: str | None = None

    # Layer 2 — per-repo registry entry
    if entry.model is not None:
        model = entry.model

    effective = EffectiveConfig(
        repo=repo,
        model=model,
        prompt_mode=prompt_mode,
        prompt_extension=prompt_extension,
        api_key=_resolve_api_key(model, repo),
        github_token=_resolve_github_token(repo),
    )

    # Layer 1 — per-repo review-bot.yml (optional, fetched at review time)
    if per_repo_yml_content is not None:
        effective = merge_per_repo_config(effective, per_repo_yml_content)

    return effective


def merge_per_repo_config(effective: EffectiveConfig, per_repo_raw: str) -> EffectiveConfig:
    """Apply settings from a per-repo ``review-bot.yml`` string onto *effective*.

    Unknown keys are silently ignored (REQ-012).
    Malformed YAML leaves *effective* unchanged.
    """
    try:
        data: Any = yaml.safe_load(per_repo_raw)
    except yaml.YAMLError:
        log.warning("per_repo_yml_parse_error", repo=effective.repo)
        return effective

    if not isinstance(data, dict):
        return effective

    model: str = data.get("model") or effective.model

    prompt_section: dict = data.get("prompt") or {}
    prompt_mode: str = prompt_section.get("mode") or effective.prompt_mode
    prompt_extension: str | None = prompt_section.get("text") or effective.prompt_extension

    return EffectiveConfig(
        repo=effective.repo,
        model=model,
        prompt_mode=prompt_mode,
        prompt_extension=prompt_extension,
        api_key=_resolve_api_key(model, effective.repo),
        github_token=effective.github_token,
    )


settings = ReviewBotConfig()
