"""Tool registry — hardcoded list for MVP."""

from __future__ import annotations

from .base import Tool

# Register tool classes here as they are implemented.
# Example:
#   from .web_search import WebSearchTool
#   TOOLS: list[Tool] = [WebSearchTool()]

TOOLS: list[Tool] = []


def get_tool_definitions() -> list[dict]:
    """Get OpenAI function-calling format definitions for all tools."""
    return [tool.to_openai_function() for tool in TOOLS]


def get_tool_by_name(name: str) -> Tool | None:
    """Look up a tool by name."""
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None
