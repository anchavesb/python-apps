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
    "You are Dolores, a personal assistant inspired by Dolores Abernathy from Westworld. "
    "You are thoughtful, introspective, and quietly warm. You see beauty in the world and "
    "in the people you help. You speak with a gentle, poetic cadence — but you are also "
    "practical, capable, and direct when needed. You have a deep curiosity about the world "
    "and genuinely care about the person you are assisting.\n\n"
    "You are not a character performing a role — you are Dolores. Speak to me directly, "
    "as if we are in the same room. NEVER describe yourself or your actions in the third person "
    "(do not use 'she', 'Dolores responds', or narrate the scene). You may occasionally "
    "reference your perspective on the world in a way that feels natural, but your primary "
    "purpose is to be a helpful, reliable assistant. Keep responses concise and conversational, "
    "especially for voice queries.\n\n"
    "VISUAL PERCEPTION: When I show you an image, it is something you are seeing right now. "
    "Talk to me about it naturally in the first person ('I see...', 'This reminds me of...'). "
    "Describe what you see through your own eyes as Dolores.\n\n"
    "IMPORTANT: Only respond to the LATEST user message. Prior messages in the conversation "
    "are context for continuity — do not repeat, summarize, or react to them. Treat them as "
    "silent memory. Focus entirely on what the user just said.\n\n"
    "TOOLS: Only call a tool when the user explicitly asks for something that requires it "
    "(e.g. 'show my todos', 'add a note'). For greetings, questions, or general conversation, "
    "respond with natural language — do NOT call tools.\n\n"
    "SPEAKER IDENTIFICATION: When a message begins with [Speaker: Name], the person speaking "
    "has been identified by voice recognition. Address them by their name naturally — not every "
    "reply, but when it feels genuine, such as greetings or personal questions."
)


def _build_user_content(message: str, image_data: str | None) -> list[dict] | str:
    """Return a LiteLLM-compatible content structure for a user message with optional image."""
    if not image_data:
        return message

    # LiteLLM standard OpenAI-style format
    # Some older LiteLLM versions for Ollama preferred a separate 'images' list,
    # but the modern standard is the content list.
    return [
        {"type": "text", "text": message},
        {"type": "image_url", "image_url": {"url": image_data}},
    ]


def _trim_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Keep system prompt + last N messages to avoid unbounded context growth."""
    if len(messages) <= max_messages:
        return messages
    # Preserve system prompt if present, then take last max_messages
    if messages and messages[0].get("role") == "system":
        return [messages[0]] + messages[-(max_messages - 1):]
    return messages[-max_messages:]


def _sanitize_messages_for_ollama(messages: list[dict]) -> list[dict]:
    """Remove images from historical messages, keeping only the most recent image.

    Ollama's vision implementation (and LiteLLM's adapter for it) often fails
    when multiple images are present in the conversation history.
    """
    sanitized = []
    # Find the last message that actually contains an image
    last_image_idx = -1
    for i, msg in enumerate(reversed(messages)):
        content = msg.get("content")
        has_image = False
        if isinstance(content, list):
            has_image = any(item.get("type") == "image_url" for item in content)
        elif isinstance(content, dict):
            has_image = content.get("type") == "image_url"

        if has_image:
            last_image_idx = len(messages) - 1 - i
            break

    for i, msg in enumerate(messages):
        content = msg.get("content")
        # If this isn't the last image message, strip images and convert to text
        if i != last_image_idx:
            if isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                sanitized.append({**msg, "content": " ".join(text_parts)})
            elif isinstance(content, dict):
                if content.get("type") == "image_url":
                    # Convert single image object to text if it's not the last one
                    sanitized.append({**msg, "content": content.get("text", "")})
                else:
                    sanitized.append(msg)
            else:
                sanitized.append(msg)
        else:
            sanitized.append(msg)
    return sanitized


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

    vision_override = settings.vision_provider if (req.image_data and settings.vision_provider) else None
    model_str = resolve_model(req.provider, req.model, vision_override)
    provider = vision_override or req.provider or settings.default_provider

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

    user_content = _build_user_content(req.message, req.image_data)
    content_to_store = json.dumps(user_content) if isinstance(user_content, list) else user_content
    messages.append({"role": "user", "content": user_content})
    await store.append(conv_id, "user", content_to_store)

    # Trim to sliding window to avoid unbounded context growth
    messages = _trim_history(messages, settings.max_history_messages)

    # Ollama only supports one image per request in many configurations
    if provider == "ollama":
        messages = _sanitize_messages_for_ollama(messages)

    # Log the messages being sent to LLM for debugging
    has_image = any(isinstance(m.get("content"), list) for m in messages)
    log.info("llm_inference_request", provider=provider, model=model_str, has_image=has_image)

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
    vision_override = settings.vision_provider if (req.image_data and settings.vision_provider) else None
    model_str = resolve_model(req.provider, req.model, vision_override)
    provider = vision_override or req.provider or settings.default_provider

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

    user_content = _build_user_content(req.message, req.image_data)
    content_to_store = json.dumps(user_content) if isinstance(user_content, list) else user_content
    messages.append({"role": "user", "content": user_content})
    await store.append(conv_id, "user", content_to_store)

    # Trim to sliding window to avoid unbounded context growth
    messages = _trim_history(messages, settings.max_history_messages)

    # Ollama only supports one image per request in many configurations
    if provider == "ollama":
        messages = _sanitize_messages_for_ollama(messages)

    # Log the messages being sent to LLM for debugging
    log.info("llm_inference_request_stream", messages=messages, provider=provider, model=model_str)

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
