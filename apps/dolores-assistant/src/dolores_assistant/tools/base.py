"""Abstract tool interface for the assistant's agent loop."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Tool(ABC):
    """Base class for assistant tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (e.g. 'web_search')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for the tool's arguments."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Run the tool and return a text result for the LLM."""
        ...

    def to_openai_function(self) -> dict:
        """Convert to OpenAI function-calling format (used by LiteLLM)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
