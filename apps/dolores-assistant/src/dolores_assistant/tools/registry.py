"""Tool registry — loads tools from OpenAPI auto-discovery at startup."""

from __future__ import annotations

import httpx

from dolores_common.logging import get_logger

from .base import Tool

log = get_logger(__name__)

TOOLS: list[Tool] = []


async def load_tools(integrations: list[dict], http_client: httpx.AsyncClient) -> None:
    """Fetch OpenAPI specs and populate the global TOOLS list."""
    global TOOLS
    if not integrations:
        return

    from .openapi_discovery import discover_tools

    discovered = await discover_tools(integrations, http_client)
    TOOLS = discovered
    log.info("tools_loaded", count=len(TOOLS), names=[t.name for t in TOOLS])


def get_tool_definitions(name_filter: set[str] | None = None) -> list[dict]:
    """Get OpenAI function-calling format definitions for tools.

    If *name_filter* is provided, only tools whose name contains one of the
    given substrings are returned (e.g. ``{"todo"}`` matches ``todo_list_todos``).
    """
    if name_filter is None:
        return [tool.to_openai_function() for tool in TOOLS]
    return [
        tool.to_openai_function()
        for tool in TOOLS
        if any(f in tool.name for f in name_filter)
    ]


def get_tool_by_name(name: str) -> Tool | None:
    """Look up a tool by name."""
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None
