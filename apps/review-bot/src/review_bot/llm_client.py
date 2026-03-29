"""LLM client module — async LiteLLM wrapper."""

from __future__ import annotations

import time

import litellm
from fastapi import HTTPException

from dolores_common.logging import get_logger

log = get_logger(__name__)

litellm.set_verbose = True


async def call_llm(model: str, messages: list[dict], api_key: str) -> str:
    """Call the LLM via LiteLLM and return the response text.

    Uses response_format={"type": "json_object"} to request structured JSON output.

    Raises:
        HTTPException(502): on any LiteLLM error.
    """
    start = time.monotonic()
    if not api_key:
        log.warning("llm_api_key_missing", model=model)
    else:
        log.info("llm_api_key_present", model=model, length=len(api_key))

    # For Gemini models, we explicitly target the stable v1 endpoint to avoid 404s
    # found on the default v1beta endpoint.
    base_url = None
    if model.startswith("gemini/"):
        base_url = "https://generativelanguage.googleapis.com/v1"

    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            base_url=base_url,
            response_format={"type": "json_object"},
        )
        elapsed = round(time.monotonic() - start, 3)
        log.info("llm_call_complete", model=model, elapsed_seconds=elapsed)
        return response.choices[0].message.content
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        log.error("llm_call_error", model=model, elapsed_seconds=elapsed, error=str(exc))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
