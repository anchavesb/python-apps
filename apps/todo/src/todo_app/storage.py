from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ISO_DT = "%Y-%m-%dT%H:%M:%SZ"

PRIORITIES = {"low", "medium", "high", "urgent"}


@dataclass
class Todo:
    id: str
    title: str
    description: Optional[str]
    tags: Dict[str, str]
    done: bool
    due_date: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class Note:
    id: str
    title: str
    note: Optional[str]
    tags: Dict[str, str]
    created_at: str
    updated_at: str


@dataclass
class RssFeed:
    id: str
    user_id: Optional[str]
    url: str
    title: str
    created_at: str


@dataclass
class RssItemState:
    id: str
    user_id: Optional[str]
    feed_id: str
    item_guid: str
    read: bool
    starred: bool
    updated_at: str


class ValidationError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_DT)


class JsonStore:
    def __init__(self, data_file: str, backups: int = 10, wal_file: str | None = None):
        self.data_file = data_file
        self.backups = int(backups)
        self.wal_file = wal_file
        self.state = {"todos": [], "notes": [], "rss_feeds": [], "rss_item_states": []}
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)

    # ---------- Validation ----------
    def _validate_tags(self, tags: Dict[str, str]):
        if not isinstance(tags, dict):
            raise ValidationError("tags must be a dict")
        required = ["category", "priority"]
        for r in required:
            if r not in tags or not isinstance(tags[r], str) or not tags[r].strip():
                raise ValidationError(f"missing required tag: {r}")
        if tags.get("priority") not in PRIORITIES:
            raise ValidationError("priority must be one of: low, medium, high, urgent")
        for k, v in tags.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValidationError("tags must be a str->str dict")

    def _validate_todo(self, data: Dict[str, Any], for_update: bool = False):
        if not for_update:
            if not data.get("title"):
                raise ValidationError("title is required")
        # Apply default tags if missing
        tags = data.get("tags") or {}
        tags.setdefault("category", "general")
        tags.setdefault("priority", "medium")
        data["tags"] = tags
        self._validate_tags(tags)
        if data.get("due_date"):
            # allow YYYY-MM-DD or ISO datetime
            dd = data["due_date"]
            if not isinstance(dd, str):
                raise ValidationError("due_date must be string in YYYY-MM-DD or ISO format")

    def _validate_note(self, data: Dict[str, Any], for_update: bool = False):
        if not for_update:
            if not data.get("title"):
                raise ValidationError("title is required")
        tags = data.get("tags") or {}
        tags.setdefault("category", "general")
        tags.setdefault("priority", "medium")
        data["tags"] = tags
        self._validate_tags(tags)

    # ---------- Persistence ----------
    def _atomic_write(self, path: str, content: str):
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            # rotate backups before replacing
            self._rotate_backups()
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _rotate_backups(self):
        # keep up to self.backups copies: data_file.bak.1 .. .bak.N
        for i in range(self.backups, 0, -1):
            src = f"{self.data_file}.bak.{i}"
            dst = f"{self.data_file}.bak.{i+1}"
            if os.path.exists(src):
                if i == self.backups:
                    os.remove(src)
                else:
                    os.replace(src, dst)
        if os.path.exists(self.data_file):
            shutil.copy2(self.data_file, f"{self.data_file}.bak.1")

    def _append_wal(self, entry: Dict[str, Any]):
        if not self.wal_file:
            return
        os.makedirs(os.path.dirname(self.wal_file), exist_ok=True)
        with open(self.wal_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _flush(self):
        content = json.dumps(self.state, ensure_ascii=False, indent=2)
        self._atomic_write(self.data_file, content)

    def load_or_recover(self):
        # Try load
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                # basic validation
                if not isinstance(self.state, dict) or "todos" not in self.state or "notes" not in self.state:
                    raise ValueError("invalid structure")
                # compatibility: ensure rss keys exist
                if "rss_feeds" not in self.state:
                    self.state["rss_feeds"] = []
                if "rss_item_states" not in self.state:
                    self.state["rss_item_states"] = []
                return
        except Exception:
            pass
        # Try backups
        for i in range(1, self.backups + 1):
            bak = f"{self.data_file}.bak.{i}"
            try:
                if os.path.exists(bak):
                    with open(bak, "r", encoding="utf-8") as f:
                        self.state = json.load(f)
                    if isinstance(self.state, dict) and "todos" in self.state and "notes" in self.state:
                        if "rss_feeds" not in self.state:
                            self.state["rss_feeds"] = []
                        if "rss_item_states" not in self.state:
                            self.state["rss_item_states"] = []
                        # After restoring from backup, try replay WAL
                        self._replay_wal()
                        self._flush()
                        return
            except Exception:
                continue
        # If no backups, start clean and try replay WAL
        self.state = {"todos": [], "notes": [], "rss_feeds": [], "rss_item_states": []}
        self._replay_wal()
        self._flush()

    def _replay_wal(self):
        if not self.wal_file or not os.path.exists(self.wal_file):
            return
        try:
            with open(self.wal_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        self._apply_wal_entry(entry)
                    except Exception:
                        continue
        except Exception:
            pass

    def _apply_wal_entry(self, e: Dict[str, Any]):
        t = e.get("type")
        if t == "todo_create":
            self.state["todos"].append(e["data"])
        elif t == "todo_update":
            for i, it in enumerate(self.state["todos"]):
                if it["id"] == e["id"]:
                    self.state["todos"][i] = e["data"]
        elif t == "todo_delete":
            self.state["todos"] = [it for it in self.state["todos"] if it["id"] != e["id"]]
        elif t == "note_create":
            self.state["notes"].append(e["data"])
        elif t == "note_update":
            for i, it in enumerate(self.state["notes"]):
                if it["id"] == e["id"]:
                    self.state["notes"][i] = e["data"]
        elif t == "note_delete":
            self.state["notes"] = [it for it in self.state["notes"] if it["id"] != e["id"]]
        elif t == "rss_feed_create":
            if "rss_feeds" not in self.state:
                self.state["rss_feeds"] = []
            self.state["rss_feeds"].append(e["data"])
        elif t == "rss_feed_delete":
            if "rss_feeds" not in self.state:
                self.state["rss_feeds"] = []
            self.state["rss_feeds"] = [it for it in self.state["rss_feeds"] if it["id"] != e["id"]]
            if "rss_item_states" in self.state:
                self.state["rss_item_states"] = [s for s in self.state["rss_item_states"] if s.get("feed_id") != e["id"]]
        elif t == "rss_item_state_update":
            if "rss_item_states" not in self.state:
                self.state["rss_item_states"] = []
            # Find and update or append
            idx = next((i for i, s in enumerate(self.state["rss_item_states"]) if s["id"] == e["data"]["id"]), None)
            if idx is not None:
                self.state["rss_item_states"][idx] = e["data"]
            else:
                self.state["rss_item_states"].append(e["data"])
            # cleanup
            if not e["data"].get("read") and not e["data"].get("starred"):
                self.state["rss_item_states"] = [s for s in self.state["rss_item_states"] if s["id"] != e["data"]["id"]]

    def validate_store(self) -> Tuple[bool, str]:
        try:
            json.dumps(self.state)
            return True, "ok"
        except Exception as e:
            return False, str(e)

    # ---------- CRUD Helpers ----------
    def _new_id(self) -> str:
        return str(uuid.uuid4())

    # Todos
    # Note: user_id parameter is accepted but ignored in single-user JSON mode
    # This allows the same calling convention as PostgresStore for multiuser mode
    def list_todos(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        return list(self.state["todos"])  # shallow copy

    def get_todo(self, tid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        return next((t for t in self.state["todos"] if t["id"] == tid), None)

    def create_todo(self, data: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        self._validate_todo(data)
        now = now_iso()
        item = {
            "id": self._new_id(),
            "title": data["title"],
            "description": data.get("description"),
            "tags": data.get("tags", {}),
            "done": bool(data.get("done", False)),
            "due_date": data.get("due_date"),
            "created_at": now,
            "updated_at": now,
        }
        self.state["todos"].append(item)
        self._append_wal({"type": "todo_create", "data": item})
        self._flush()
        return item

    def update_todo(self, tid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        idx = next((i for i, t in enumerate(self.state["todos"]) if t["id"] == tid), None)
        if idx is None:
            return None
        current = self.state["todos"][idx]
        merged = {
            **current,
            **{k: v for k, v in data.items() if v is not None},
            "updated_at": now_iso(),
        }
        self._validate_todo(merged, for_update=True)
        self.state["todos"][idx] = merged
        self._append_wal({"type": "todo_update", "id": tid, "data": merged})
        self._flush()
        return merged

    def delete_todo(self, tid: str, user_id: str | None = None) -> bool:
        before = len(self.state["todos"])
        self.state["todos"] = [t for t in self.state["todos"] if t["id"] != tid]
        deleted = len(self.state["todos"]) < before
        if deleted:
            self._append_wal({"type": "todo_delete", "id": tid})
            self._flush()
        return deleted

    # Notes
    def list_notes(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        return list(self.state["notes"])

    def get_note(self, nid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        return next((n for n in self.state["notes"] if n["id"] == nid), None)

    def create_note(self, data: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        self._validate_note(data)
        now = now_iso()
        item = {
            "id": self._new_id(),
            "title": data["title"],
            "note": data.get("note"),
            "tags": data.get("tags", {}),
            "created_at": now,
            "updated_at": now,
        }
        self.state["notes"].append(item)
        self._append_wal({"type": "note_create", "data": item})
        self._flush()
        return item

    def update_note(self, nid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        idx = next((i for i, n in enumerate(self.state["notes"]) if n["id"] == nid), None)
        if idx is None:
            return None
        current = self.state["notes"][idx]
        merged = {
            **current,
            **{k: v for k, v in data.items() if v is not None},
            "updated_at": now_iso(),
        }
        self._validate_note(merged, for_update=True)
        self.state["notes"][idx] = merged
        self._append_wal({"type": "note_update", "id": nid, "data": merged})
        self._flush()
        return merged

    def delete_note(self, nid: str, user_id: str | None = None) -> bool:
        before = len(self.state["notes"])
        self.state["notes"] = [n for n in self.state["notes"] if n["id"] != nid]
        deleted = len(self.state["notes"]) < before
        if deleted:
            self._append_wal({"type": "note_delete", "id": nid})
            self._flush()
        return deleted
    # RSS Feeds
    def list_rss_feeds(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        if "rss_feeds" not in self.state:
            self.state["rss_feeds"] = []
        return [f for f in self.state["rss_feeds"] if not user_id or f.get("user_id") == user_id]

    def create_rss_feed(self, data: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        if "rss_feeds" not in self.state:
            self.state["rss_feeds"] = []
        now = now_iso()
        feed = {
            "id": self._new_id(),
            "user_id": user_id,
            "url": data["url"],
            "title": data.get("title") or "Unnamed Feed",
            "created_at": now,
        }
        self.state["rss_feeds"].append(feed)
        self._append_wal({"type": "rss_feed_create", "data": feed})
        self._flush()
        return feed

    def delete_rss_feed(self, feed_id: str, user_id: str | None = None) -> bool:
        if "rss_feeds" not in self.state:
            self.state["rss_feeds"] = []
        before = len(self.state["rss_feeds"])
        self.state["rss_feeds"] = [
            f for f in self.state["rss_feeds"]
            if f["id"] != feed_id or (user_id and f.get("user_id") != user_id)
        ]
        deleted = len(self.state["rss_feeds"]) < before
        if deleted:
            if "rss_item_states" in self.state:
                self.state["rss_item_states"] = [
                    s for s in self.state["rss_item_states"] if s.get("feed_id") != feed_id
                ]
            self._append_wal({"type": "rss_feed_delete", "id": feed_id})
            self._flush()
        return deleted

    # RSS Item States
    def get_rss_item_states(self, user_id: str | None = None, feed_id: str | None = None) -> List[Dict[str, Any]]:
        if "rss_item_states" not in self.state:
            self.state["rss_item_states"] = []
        res = self.state["rss_item_states"]
        if user_id:
            res = [s for s in res if s.get("user_id") == user_id]
        if feed_id:
            res = [s for s in res if s.get("feed_id") == feed_id]
        return res

    def update_rss_item_state(self, user_id: str | None, feed_id: str, item_guid: str, read: bool | None = None, starred: bool | None = None) -> Dict[str, Any]:
        if "rss_item_states" not in self.state:
            self.state["rss_item_states"] = []

        state = next((s for s in self.state["rss_item_states"] if s.get("user_id") == user_id and s.get("feed_id") == feed_id and s.get("item_guid") == item_guid), None)

        now = now_iso()
        if not state:
            state = {
                "id": self._new_id(),
                "user_id": user_id,
                "feed_id": feed_id,
                "item_guid": item_guid,
                "read": False,
                "starred": False,
                "updated_at": now,
            }
            self.state["rss_item_states"].append(state)

        if read is not None:
            state["read"] = read
        if starred is not None:
            state["starred"] = starred
        state["updated_at"] = now

        if not state["read"] and not state["starred"]:
            self.state["rss_item_states"] = [s for s in self.state["rss_item_states"] if s["id"] != state["id"]]

        self._append_wal({"type": "rss_item_state_update", "data": state})
        self._flush()
        return state

    def mark_all_rss_items_read(self, user_id: str | None, feed_id: str, item_guids: List[str]):
        if "rss_item_states" not in self.state:
            self.state["rss_item_states"] = []
        for guid in item_guids:
            self.update_rss_item_state(user_id, feed_id, guid, read=True)
