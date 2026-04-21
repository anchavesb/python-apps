from __future__ import annotations

from dolores_common.logging import get_logger

from ..memory import MemoryStore
from .base import Tool

log = get_logger(__name__)

class MemoryStoreTool(Tool):
    """Explicitly store a fact in long-term memory."""

    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store

    @property
    def name(self) -> str:
        return "memory_store_fact"

    @property
    def description(self) -> str:
        return (
            "Store an important fact about the user or their preferences in long-term memory. "
            "Use this for things they want you to remember across conversations."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember (e.g. 'The user's favorite color is blue').",
                },
            },
            "required": ["fact"],
        }

    async def execute(self, **kwargs) -> str:
        fact: str = kwargs.get("fact", "")
        if not fact:
            return "No fact provided."

        await self._memory.add_memory(fact)
        return f"Fact stored in long-term memory: {fact}"
