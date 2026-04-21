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

    async def ensure_initialized(self):
        if self._initialized:
            return
        
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            await db.commit()
        
        self._initialized = True
        log.info("memory_store_initialized", path=self.db_path)

    async def add_memory(self, text: str, metadata: Optional[dict] = None):
        """Store a new fact with its embedding."""
        await self.ensure_initialized()
        
        memory_id = str(uuid.uuid4())
        embedding = get_embedding(text)
        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memories (id, text, embedding, metadata) VALUES (?, ?, ?, ?)",
                (memory_id, text, embedding_blob, json.dumps(metadata or {}))
            )
            await db.commit()
        
        log.info("memory_added", text=text[:50])

    async def search_memories(self, query: str, limit: int = 5, min_score: float = 0.5) -> List[dict]:
        """Find relevant memories using cosine similarity.
        
        Optimized by limiting scan to most recent 100 entries to avoid Python overhead.
        """
        await self.ensure_initialized()
        
        query_embedding = np.array(get_embedding(query), dtype=np.float32)
        
        memories = []
        async with aiosqlite.connect(self.db_path) as db:
            # Avoid full table scan as it grows - scan most recent first
            async with db.execute(
                "SELECT text, embedding, metadata, timestamp FROM memories ORDER BY timestamp DESC LIMIT 100"
            ) as cursor:
                async for row in cursor:
                    text, emb_blob, meta_json, ts = row
                    emb = np.frombuffer(emb_blob, dtype=np.float32)
                    
                    # Cosine similarity (since embeddings are normalized by _encode)
                    score = float(np.dot(query_embedding, emb))
                    
                    if score >= min_score:
                        memories.append({
                            "text": text,
                            "score": score,
                            "metadata": json.loads(meta_json),
                            "timestamp": ts
                        })
        
        # Sort by score descending
        memories.sort(key=lambda x: x["score"], reverse=True)
        return memories[:limit]
