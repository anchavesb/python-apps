"""aiosqlite-backed PR state store — last-seen head SHA per (repo, pr_number)."""

from __future__ import annotations

import aiosqlite

from dolores_common.logging import get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pr_state (
    repo            TEXT    NOT NULL,
    pr_number       INTEGER NOT NULL,
    head_sha        TEXT    NOT NULL,
    last_comment_id INTEGER,
    PRIMARY KEY (repo, pr_number)
)
"""


class StateStore:
    """Async SQLite store tracking the last-reviewed head SHA and comment ID per PR."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open the database and create the pr_state table if it does not exist."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        # Migrate: add last_comment_id if it doesn't exist
        try:
            await self._db.execute("ALTER TABLE pr_state ADD COLUMN last_comment_id INTEGER")
        except aiosqlite.OperationalError:
            # Column already exists
            pass
        await self._db.commit()
        log.info("state_store_ready", db_path=self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()

    async def get_sha(self, repo: str, pr_number: int) -> str | None:
        """Return the last-seen head SHA for the given (repo, pr_number), or None."""
        async with self._db.execute(
            "SELECT head_sha FROM pr_state WHERE repo = ? AND pr_number = ?",
            (repo, pr_number),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_last_comment_id(self, repo: str, pr_number: int) -> int | None:
        """Return the last-processed comment ID for the given (repo, pr_number), or None."""
        async with self._db.execute(
            "SELECT last_comment_id FROM pr_state WHERE repo = ? AND pr_number = ?",
            (repo, pr_number),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_state(self, repo: str, pr_number: int, head_sha: str, last_comment_id: int | None) -> None:
        """Upsert the state for the given (repo, pr_number)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO pr_state (repo, pr_number, head_sha, last_comment_id) VALUES (?, ?, ?, ?)",
            (repo, pr_number, head_sha, last_comment_id),
        )
        await self._db.commit()

    async def set_sha(self, repo: str, pr_number: int, head_sha: str) -> None:
        """Upsert the head SHA for the given (repo, pr_number), preserving last_comment_id."""
        last_comment_id = await self.get_last_comment_id(repo, pr_number)
        await self.set_state(repo, pr_number, head_sha, last_comment_id)


_store: StateStore | None = None


def set_state_store(store: StateStore) -> None:
    """Register the global StateStore singleton."""
    global _store
    _store = store


def get_state_store() -> StateStore:
    """Return the global StateStore singleton, raising RuntimeError if uninitialized."""
    if _store is None:
        raise RuntimeError("StateStore not initialized")
    return _store
