"""Voice profile management backed by filesystem + SQLite."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from dolores_common.logging import get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS voice_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    engine TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class VoiceProfileStore:
    """Manages voice profiles: reference audio on disk, metadata in SQLite."""

    def __init__(self, voices_dir: str, db_path: str) -> None:
        self._voices_dir = Path(voices_dir)
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._voices_dir.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.commit()
        log.info("voice_profile_store_ready")

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def create(
        self, name: str, audio_data: bytes, engine: str = "coqui_xtts", description: str = ""
    ) -> dict:
        """Create a new voice profile from reference audio."""
        profile_id = str(uuid.uuid4())[:8]
        profile_dir = self._voices_dir / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Save reference audio
        ref_path = profile_dir / "reference.wav"
        ref_path.write_bytes(audio_data)

        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO voice_profiles (id, name, description, engine, created_at) VALUES (?, ?, ?, ?, ?)",
            (profile_id, name, description, engine, now),
        )
        await self._db.commit()

        log.info("voice_profile_created", id=profile_id, name=name)
        return {"id": profile_id, "name": name, "engine": engine}

    async def list_profiles(self) -> list[dict]:
        """List all voice profiles."""
        cursor = await self._db.execute(
            "SELECT id, name, description, engine, created_at FROM voice_profiles ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "description": r[2], "engine": r[3], "created_at": r[4]}
            for r in rows
        ]

    async def delete(self, profile_id: str) -> bool:
        """Delete a voice profile."""
        profile_dir = self._voices_dir / profile_id
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

        cursor = await self._db.execute(
            "DELETE FROM voice_profiles WHERE id = ?", (profile_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0
