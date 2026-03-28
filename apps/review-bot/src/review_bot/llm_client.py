"""LLM client module — async LiteLLM wrapper."""

from __future__ import annotations

import time

import litellm
from fastapi import HTTPException

from dolores_common.logging import get_logger

log = get_logger(__name__)


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
