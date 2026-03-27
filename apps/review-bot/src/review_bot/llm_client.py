"""LLM client module — async LiteLLM wrapper with per-repo API key resolution."""

from __future__ import annotations

import os
import time

import litellm
from fastapi import HTTPException

from dolores_common.logging import get_logger

log = get_logger(__name__)


def resolve_api_key(model: str, repo: str) -> str:
    """Resolve the API key for the given model and repo.

    Resolution order:
    1. Per-repo env var: REPO_<SAFE_NAME>_GEMINI_API_KEY or REPO_<SAFE_NAME>_ANTHROPIC_API_KEY
    2. Shared env var: GEMINI_API_KEY or ANTHROPIC_API_KEY

    <SAFE_NAME> is derived by uppercasing owner/repo and replacing '/' and '-' with '_'.

    Raises:
        ValueError: if no key is found for the resolved provider.
    """
    safe_name = repo.upper().replace("/", "_").replace("-", "_")
    provider = "GEMINI" if model.startswith("gemini/") else "ANTHROPIC"

    per_repo_var = f"REPO_{safe_name}_{provider}_API_KEY"
    per_repo_key = os.getenv(per_repo_var)
    if per_repo_key:
        return per_repo_key

    shared_var = "GEMINI_API_KEY" if provider == "GEMINI" else "ANTHROPIC_API_KEY"
    shared_key = os.getenv(shared_var)
    if not shared_key:
        raise ValueError(f"No API key found for model {model!r} and repo {repo!r}. Set {per_repo_var} or {shared_var}.")
    return shared_key


async def call_llm(model: str, messages: list[dict], api_key: str) -> str:
    """Call the LLM via LiteLLM and return the response text.

    Uses response_format={"type": "json_object"} to request structured JSON output.

    Raises:
        HTTPException(502): on any LiteLLM error.
    """
    start = time.monotonic()
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            response_format={"type": "json_object"},
        )
        elapsed = round(time.monotonic() - start, 3)
        log.info("llm_call_complete", model=model, elapsed_seconds=elapsed)
        return response.choices[0].message.content
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        log.error("llm_call_error", model=model, elapsed_seconds=elapsed, error=str(exc))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
