from __future__ import annotations
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
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
class WorkItem:
    id: str
    name: str
    start_date: str
    end_date: Optional[str]
    description: Optional[str]
    why: Optional[str]
    created_at: str
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
        self.state = {"todos": [], "notes": [], "work_items": []}
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
        tags = data.get("tags", {})
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
        tags = data.get("tags", {})
        self._validate_tags(tags)

    def _validate_work(self, data: Dict[str, Any], for_update: bool = False):
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("name is required")
        sd = data.get("start_date")
        if not isinstance(sd, str) or not sd:
            raise ValidationError("start_date is required (YYYY-MM-DD)")
        try:
            sdate = date.fromisoformat(sd[:10])
        except Exception:
            raise ValidationError("start_date must be YYYY-MM-DD")
        ed = data.get("end_date")
        if ed:
            if not isinstance(ed, str):
                raise ValidationError("end_date must be string YYYY-MM-DD")
            try:
                edate = date.fromisoformat(ed[:10])
            except Exception:
                raise ValidationError("end_date must be YYYY-MM-DD")
            if edate < sdate:
                raise ValidationError("end_date cannot be earlier than start_date")

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
                # compatibility: ensure work_items exists
                if "work_items" not in self.state:
                    self.state["work_items"] = []
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
                        if "work_items" not in self.state:
                            self.state["work_items"] = []
                        # After restoring from backup, try replay WAL
                        self._replay_wal()
                        self._flush()
                        return
            except Exception:
                continue
        # If no backups, start clean and try replay WAL
        self.state = {"todos": [], "notes": [], "work_items": []}
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
        elif t == "work_create":
            self.state["work_items"].append(e["data"])
        elif t == "work_update":
            for i, it in enumerate(self.state["work_items"]):
                if it["id"] == e["id"]:
                    self.state["work_items"][i] = e["data"]
        elif t == "work_delete":
            self.state["work_items"] = [it for it in self.state["work_items"] if it["id"] != e["id"]]

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
    # Work Items
    def list_work(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        return list(self.state["work_items"])  # shallow copy

    def get_work(self, wid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        return next((w for w in self.state["work_items"] if w["id"] == wid), None)

    def create_work(self, data: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        self._validate_work(data)
        now = now_iso()
        item = {
            "id": self._new_id(),
            "name": data["name"],
            "start_date": data["start_date"],
            "end_date": data.get("end_date"),
            "description": data.get("description"),
            "why": data.get("why"),
            "created_at": now,
            "updated_at": now,
        }
        self.state["work_items"].append(item)
        self._append_wal({"type": "work_create", "data": item})
        self._flush()
        return item

    def update_work(self, wid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        idx = next((i for i, w in enumerate(self.state["work_items"]) if w["id"] == wid), None)
        if idx is None:
            return None
        current = self.state["work_items"][idx]
        merged = {
            **current,
            **{k: v for k, v in data.items() if v is not None},
            "updated_at": now_iso(),
        }
        self._validate_work(merged, for_update=True)
        self.state["work_items"][idx] = merged
        self._append_wal({"type": "work_update", "id": wid, "data": merged})
        self._flush()
        return merged

    def delete_work(self, wid: str, user_id: str | None = None) -> bool:
        before = len(self.state["work_items"])
        self.state["work_items"] = [w for w in self.state["work_items"] if w["id"] != wid]
        deleted = len(self.state["work_items"]) < before
        if deleted:
            self._append_wal({"type": "work_delete", "id": wid})
            self._flush()
        return deleted
