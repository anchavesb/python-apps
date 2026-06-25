import base64
import json

from dolores_common.logging import get_logger

from ..memory import MemoryStore
from .base import Tool
from .openapi_discovery import current_user_token

log = get_logger(__name__)


def _get_current_user_id() -> str:
    """Extract sub/email user ID claim from current OIDC token context."""
    token = current_user_token.get()
    if not token:
        return "anonymous"
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("sub") or data.get("email") or "anonymous"
    except Exception:
        return "anonymous"


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

        user_id = _get_current_user_id()
        await self._memory.add_memory(fact, user_id=user_id)
        return f"Fact stored in long-term memory: {fact}"

