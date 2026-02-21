"""Brain API routes: POST /v1/chat, POST /v1/chat/stream, GET /v1/providers."""

from __future__ import annotations

import json
import time

import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from dolores_common.auth import ServicePSK
from dolores_common.logging import get_logger

from .config import settings
from .conversation import ConversationStore
from .provider_config import PROVIDERS, resolve_model
from .schemas import ChatRequest, ChatResponse, ProviderInfo

log = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["brain"])

_store: ConversationStore | None = None

DEFAULT_SYSTEM_PROMPT = (
    "You are Dolores, a helpful and friendly personal assistant. "
    "Be concise and natural in your responses. When answering voice queries, "
    "keep responses short and conversational."
)


def get_store() -> ConversationStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Conversation store not initialized")
    return _store


def set_store(store: ConversationStore) -> None:
    global _store
    _store = store


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _auth: ServicePSK = None,
    store: ConversationStore = Depends(get_store),
) -> ChatResponse:
    """Non-streaming chat completion."""
    start = time.monotonic()

    model_str = resolve_model(req.provider, req.model)
    provider = req.provider or settings.default_provider

    # Get or create conversation
    conv_id = req.conversation_id
    if conv_id and await store.exists(conv_id):
        messages = await store.get_history(conv_id)
    else:
        conv_id = await store.create(conv_id)
        messages = []

    # Add system prompt if not already present
    system_prompt = req.system_prompt or DEFAULT_SYSTEM_PROMPT
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})

    # Append user message
    messages.append({"role": "user", "content": req.message})
    await store.append(conv_id, "user", req.message)

    # Call LiteLLM
    kwargs: dict = {
        "model": model_str,
        "messages": messages,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }
    if req.tools:
        kwargs["tools"] = req.tools

    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as e:
        log.error("llm_error", provider=provider, model=model_str, error=str(e))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    choice = response.choices[0]
    assistant_msg = choice.message.content or ""
    tool_calls = []

    if choice.message.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in choice.message.tool_calls
        ]

    # Store assistant response
    await store.append(conv_id, "assistant", assistant_msg, tool_calls=tool_calls or None)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    log.info(
        "chat_complete",
        provider=provider,
        model=model_str,
        conversation_id=conv_id,
        processing_time_ms=elapsed_ms,
        tokens=usage.get("total_tokens") if usage else None,
    )

    return ChatResponse(
        conversation_id=conv_id,
        message=assistant_msg,
        provider=provider,
        model=model_str,
        usage=usage,
        tool_calls=tool_calls,
        processing_time_ms=elapsed_ms,
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    _auth: ServicePSK = None,
    store: ConversationStore = Depends(get_store),
) -> StreamingResponse:
    """Streaming chat completion via SSE."""
    model_str = resolve_model(req.provider, req.model)
    provider = req.provider or settings.default_provider

    # Get or create conversation
    conv_id = req.conversation_id
    if conv_id and await store.exists(conv_id):
        messages = await store.get_history(conv_id)
    else:
        conv_id = await store.create(conv_id)
        messages = []

    system_prompt = req.system_prompt or DEFAULT_SYSTEM_PROMPT
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": req.message})
    await store.append(conv_id, "user", req.message)

    kwargs: dict = {
        "model": model_str,
        "messages": messages,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "stream": True,
    }
    if req.tools:
        kwargs["tools"] = req.tools

    async def generate():
        full_text = ""
        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_text += delta.content
                    yield f"data: {json.dumps({'type': 'token', 'content': delta.content, 'conversation_id': conv_id})}\n\n"

            # Store full response
            await store.append(conv_id, "assistant", full_text)

            yield f"data: {json.dumps({'type': 'done', 'content': full_text, 'conversation_id': conv_id, 'provider': provider, 'model': model_str})}\n\n"

        except Exception as e:
            log.error("stream_error", provider=provider, model=model_str, error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers(_auth: ServicePSK = None) -> list[ProviderInfo]:
    """List available LLM providers and their models."""
    return [
        ProviderInfo(
            name=info["name"],
            models=info["models"],
            default_model=info["default_model"],
        )
        for info in PROVIDERS.values()
    ]
