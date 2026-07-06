import asyncio
import json
import uuid
from pathlib import Path
from typing import List, Optional

import aiosqlite
import numpy as np

from dolores_common.logging import get_logger

from .config import settings
from .intent import get_embedding

log = get_logger(__name__)


class MemoryStore:
    """Long-term memory using SQLite + embeddings for semantic search."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.memory_db_path
        self._initialized = False
        self._db: Optional[aiosqlite.Connection] = None
        # Lazily created inside ensure_initialized to avoid RuntimeError when
        # instantiated before the event loop starts (Python 3.11+).
        self._lock: Optional[asyncio.Lock] = None

    async def ensure_initialized(self):
        if self._initialized and self._db:
            return

        # Lazily create the lock the first time we reach here (inside the event loop).
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            # Re-check inside the lock in case another coroutine already initialized
            if self._initialized and self._db:
                return

            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            if not self._db:
                self._db = await aiosqlite.connect(self.db_path)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'anonymous',
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            # Migrations: Add user_id column if table already existed without it
            try:
                await self._db.execute("ALTER TABLE memories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'anonymous'")
            except aiosqlite.OperationalError:
                pass # column already exists

            # Drop old single-column index if it exists (superseded by composite index below)
            await self._db.execute("DROP INDEX IF EXISTS idx_memories_user")
            await self._db.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_timestamp ON memories(user_id, timestamp DESC)")
            await self._db.commit()

            self._initialized = True
            log.info("memory_store_initialized", path=self.db_path)

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False

    async def add_memory(self, text: str, user_id: str = "anonymous", metadata: Optional[dict] = None):
        """Store a new fact with its embedding."""
        await self.ensure_initialized()
        assert self._db is not None

        memory_id = str(uuid.uuid4())
        embedding = get_embedding(text)
        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

        await self._db.execute(
            "INSERT INTO memories (id, user_id, text, embedding, metadata) VALUES (?, ?, ?, ?, ?)",
            (memory_id, user_id, text, embedding_blob, json.dumps(metadata or {})),
        )
        await self._db.commit()

        log.info("memory_added", user_id=user_id, text=text[:50])

    async def search_memories(self, query: str, user_id: str = "anonymous", limit: int = 5, min_score: float = 0.5) -> List[dict]:
        """Find relevant memories using cosine similarity.

        Optimized by limiting scan to most recent 500 entries to avoid Python overhead.
        """
        await self.ensure_initialized()
        assert self._db is not None

        query_embedding = np.array(get_embedding(query), dtype=np.float32)

        memories = []
        # Avoid full table scan as it grows - scan most recent first for this user
        async with self._db.execute(
            "SELECT text, embedding, metadata, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 500",
            (user_id,)
        ) as cursor:
            async for row in cursor:
                text, emb_blob, meta_json, ts = row
                emb = np.frombuffer(emb_blob, dtype=np.float32)

                # Cosine similarity (since embeddings are normalized by _encode)
                score = float(np.dot(query_embedding, emb))

                if score >= min_score:
                    memories.append(
                        {
                            "text": text,
                            "score": score,
                            "metadata": json.loads(meta_json),
                            "timestamp": ts,
                        }
                    )

        # Sort by score descending
        memories.sort(key=lambda x: x["score"], reverse=True)
        return memories[:limit]
