"""LLM client module — async LiteLLM wrapper."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable

import litellm

from dolores_common.logging import get_logger

log = get_logger(__name__)

litellm.set_verbose = False


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> Callable:
    """Decorator to retry an async function with exponential backoff on LiteLLM errors."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    # Check if this is a rate limit or overloaded error
                    error_str = str(exc).lower()
                    is_retryable = any(
                        token in error_str
                        for token in ["429", "rate limit", "overloaded", "503", "too many requests"]
                    )

                    if not is_retryable or attempt >= max_retries:
                        log.error("llm_call_final_failure", attempt=attempt, error=str(exc))
                        raise

                    log.warning(
                        "llm_call_retryable_error",
                        attempt=attempt,
                        error=str(exc),
                        next_delay=delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor

            return await func(*args, **kwargs)

        return wrapper

    return decorator


@retry_with_backoff(max_retries=3, initial_delay=30.0)
async def call_llm(model: str, messages: list[dict], api_key: str) -> str:
    """Call the LLM via LiteLLM and return the response text.

    Uses response_format={"type": "json_object"} to request structured JSON output.

    Raises:
        HTTPException(502): on any LiteLLM error.
    """
    start = time.monotonic()
    if not api_key:
        log.warning("llm_api_key_missing", model=model)

    # For Gemini models, we explicitly target the v1beta endpoint to support
    # system_instruction and response_mime_type (JSON mode), which are not yet
    # available in the stable v1 endpoint.
    base_url = None
    actual_model = model
    if model.startswith("gemini/"):
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        actual_model = model.split("/", 1)[1]

    try:
        response = await litellm.acompletion(
            model=actual_model,
            messages=messages,
            api_key=api_key,
            base_url=base_url,
            custom_llm_provider="gemini",
            api_version="v1beta",
            response_format={"type": "json_object"},
        )

        elapsed = round(time.monotonic() - start, 3)
        log.info("llm_call_complete", model=model, elapsed_seconds=elapsed)
        return response.choices[0].message.content
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        # We don't log the error as 'error' here because the decorator will handle
        # logging and retrying. If it's a final failure, the decorator logs it.
        log.debug("llm_call_attempt_failed", model=model, elapsed_seconds=elapsed, error=str(exc))
        raise
