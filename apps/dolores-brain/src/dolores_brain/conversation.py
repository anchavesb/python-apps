"""SQLite-backed conversation store."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from dolores_common.logging import get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);
"""

_CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_call_id TEXT,
    tool_calls TEXT,
    created_at TEXT NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
"""


class ConversationStore:
    """Async SQLite store for conversation history."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open the database and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.execute(_CREATE_MESSAGES_TABLE)
        await self._db.execute(_CREATE_INDEX)
        await self._db.commit()
        log.info("conversation_store_ready", db_path=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def create(self, conversation_id: str | None = None) -> str:
        """Create a new conversation and return its ID."""
        cid = conversation_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
            (cid, now, now),
        )
        await self._db.commit()
        return cid

    async def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_calls: list[dict] | None = None,
    ) -> None:
        """Append a message to a conversation."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_call_id, tool_calls, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                tool_call_id,
                json.dumps(tool_calls) if tool_calls else None,
                now,
            ),
        )
        await self._db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await self._db.commit()

    async def get_history(self, conversation_id: str) -> list[dict]:
        """Get all messages for a conversation in order."""
        cursor = await self._db.execute(
            "SELECT role, content, tool_call_id, tool_calls FROM messages "
            "WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        messages = []
        for role, content, tool_call_id, tool_calls_json in rows:
            msg: dict = {"role": role, "content": content}
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id
            if tool_calls_json:
                msg["tool_calls"] = json.loads(tool_calls_json)
            messages.append(msg)
        return messages

    async def exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists."""
        cursor = await self._db.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
        )
        return await cursor.fetchone() is not None

    async def list_conversations(self, limit: int = 50) -> list[dict]:
        """List recent conversations."""
        cursor = await self._db.execute(
            "SELECT id, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {"id": cid, "created_at": created, "updated_at": updated}
            for cid, created, updated in rows
        ]
