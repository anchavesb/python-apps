"""SQLite store for speaker voice profiles."""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone

import numpy as np

from dolores_common.logging import get_logger

log = get_logger(__name__)

_NAME_RE = re.compile(r"^[a-zA-Z0-9 ]{1,32}$")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    embedding BLOB NOT NULL,
    embedding_version TEXT NOT NULL,
    samples_count INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpeakerStore:
    """Persistent speaker profile storage backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL mode for safe concurrent reads from asyncio.to_thread workers
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            raise RuntimeError("SpeakerStore not opened")
        return self._conn

    @staticmethod
    def validate_name(name: str) -> str:
        """Validate and sanitize speaker name. Raises ValueError on bad input."""
        name = name.strip()
        if not _NAME_RE.match(name):
            raise ValueError(
                "Speaker name must be 1-32 characters, alphanumeric and spaces only"
            )
        return name

    def enroll(
        self,
        name: str,
        embeddings: list[np.ndarray],
        email: str | None = None,
        embedding_version: str = "resemblyzer-0.1.3",
    ) -> dict:
        """Enroll a new speaker from one or more embedding vectors."""
        name = self.validate_name(name)
        avg_embedding = np.mean(embeddings, axis=0).astype(np.float32)
        speaker_id = str(uuid.uuid4())
        now = _now_iso()

        self.conn.execute(
            "INSERT INTO speakers (id, name, email, embedding, embedding_version, samples_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                speaker_id,
                name,
                email,
                avg_embedding.tobytes(),
                embedding_version,
                len(embeddings),
                now,
                now,
            ),
        )
        self.conn.commit()
        log.info("speaker_enrolled", id=speaker_id, name=name, samples=len(embeddings))
        return {"id": speaker_id, "name": name, "email": email, "samples_count": len(embeddings)}

    def update_embedding(
        self,
        speaker_id: str,
        new_embedding: np.ndarray,
    ) -> bool:
        """Update speaker embedding with running average."""
        row = self.conn.execute(
            "SELECT embedding, samples_count FROM speakers WHERE id = ?", (speaker_id,)
        ).fetchone()
        if not row:
            return False

        old_emb = np.frombuffer(row["embedding"], dtype=np.float32)
        count = row["samples_count"]
        # Running average
        updated = ((old_emb * count) + new_embedding) / (count + 1)
        updated = updated.astype(np.float32)

        self.conn.execute(
            "UPDATE speakers SET embedding = ?, samples_count = ?, updated_at = ? WHERE id = ?",
            (updated.tobytes(), count + 1, _now_iso(), speaker_id),
        )
        self.conn.commit()
        return True

    def list_speakers(self) -> list[dict]:
        """List all speakers (without embeddings)."""
        rows = self.conn.execute(
            "SELECT id, name, email, samples_count, created_at, updated_at FROM speakers ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_with_embeddings(self) -> list[dict]:
        """List all speakers with decoded embeddings.

        Note: loads all embeddings into memory. Fine for the expected scale
        (household/small-team, <100 speakers). For larger deployments,
        consider approximate nearest-neighbor search (e.g. FAISS).
        """
        rows = self.conn.execute(
            "SELECT id, name, email, embedding, embedding_version, samples_count FROM speakers"
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "email": r["email"],
                "embedding": np.frombuffer(r["embedding"], dtype=np.float32),
                "embedding_version": r["embedding_version"],
                "samples_count": r["samples_count"],
            })
        return result

    def get(self, speaker_id: str) -> dict | None:
        """Get a single speaker profile."""
        row = self.conn.execute(
            "SELECT id, name, email, samples_count, created_at, updated_at FROM speakers WHERE id = ?",
            (speaker_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete(self, speaker_id: str) -> bool:
        """Delete a speaker profile. Returns True if deleted."""
        cursor = self.conn.execute("DELETE FROM speakers WHERE id = ?", (speaker_id,))
        self.conn.commit()
        return cursor.rowcount > 0
