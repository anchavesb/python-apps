"""PostgreSQL storage backend with multiuser support."""
from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, User, Todo, Note, WorkItem
from .storage import ValidationError, PRIORITIES


class PostgresStore:
    """PostgreSQL-backed storage with user isolation."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

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

    # ---------- User Management ----------
    def get_or_create_user(self, user_id: str, email: str | None = None, name: str | None = None) -> User:
        """Get existing user or create new one."""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if not user:
                user = User(id=user_id, email=email, name=name)
                session.add(user)
                session.commit()
                session.refresh(user)
            elif email or name:
                # Update user info if provided
                if email:
                    user.email = email
                if name:
                    user.name = name
                session.commit()
                session.refresh(user)
            return user

    # ---------- Health Check ----------
    def validate_store(self) -> Tuple[bool, str]:
        try:
            with self.get_session() as session:
                session.execute(select(1))
            return True, "ok"
        except Exception as e:
            return False, str(e)

    # ---------- Todos ----------
    def list_todos(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Todo)
            if user_id:
                query = query.where(Todo.user_id == user_id)
            todos = session.execute(query).scalars().all()
            return [t.to_dict() for t in todos]

    def get_todo(self, tid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Todo).where(Todo.id == tid)
            if user_id:
                query = query.where(Todo.user_id == user_id)
            todo = session.execute(query).scalar_one_or_none()
            return todo.to_dict() if todo else None

    def create_todo(self, data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        self._validate_todo(data)
        with self.get_session() as session:
            # Ensure user exists
            self.get_or_create_user(user_id)
            todo = Todo(
                user_id=user_id,
                title=data["title"],
                description=data.get("description"),
                tags=data.get("tags", {}),
                done=bool(data.get("done", False)),
                due_date=data.get("due_date"),
            )
            session.add(todo)
            session.commit()
            session.refresh(todo)
            return todo.to_dict()

    def update_todo(self, tid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Todo).where(Todo.id == tid)
            if user_id:
                query = query.where(Todo.user_id == user_id)
            todo = session.execute(query).scalar_one_or_none()
            if not todo:
                return None

            # Merge data
            merged = todo.to_dict()
            merged.update({k: v for k, v in data.items() if v is not None})
            self._validate_todo(merged, for_update=True)

            # Apply updates
            if "title" in data:
                todo.title = data["title"]
            if "description" in data:
                todo.description = data["description"]
            if "tags" in data:
                todo.tags = data["tags"]
            if "done" in data:
                todo.done = data["done"]
            if "due_date" in data:
                todo.due_date = data["due_date"]

            session.commit()
            session.refresh(todo)
            return todo.to_dict()

    def delete_todo(self, tid: str, user_id: str | None = None) -> bool:
        with self.get_session() as session:
            query = select(Todo).where(Todo.id == tid)
            if user_id:
                query = query.where(Todo.user_id == user_id)
            todo = session.execute(query).scalar_one_or_none()
            if not todo:
                return False
            session.delete(todo)
            session.commit()
            return True

    # ---------- Notes ----------
    def list_notes(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Note)
            if user_id:
                query = query.where(Note.user_id == user_id)
            notes = session.execute(query).scalars().all()
            return [n.to_dict() for n in notes]

    def get_note(self, nid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Note).where(Note.id == nid)
            if user_id:
                query = query.where(Note.user_id == user_id)
            note = session.execute(query).scalar_one_or_none()
            return note.to_dict() if note else None

    def create_note(self, data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        self._validate_note(data)
        with self.get_session() as session:
            self.get_or_create_user(user_id)
            note = Note(
                user_id=user_id,
                title=data["title"],
                note=data.get("note"),
                tags=data.get("tags", {}),
            )
            session.add(note)
            session.commit()
            session.refresh(note)
            return note.to_dict()

    def update_note(self, nid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Note).where(Note.id == nid)
            if user_id:
                query = query.where(Note.user_id == user_id)
            note = session.execute(query).scalar_one_or_none()
            if not note:
                return None

            merged = note.to_dict()
            merged.update({k: v for k, v in data.items() if v is not None})
            self._validate_note(merged, for_update=True)

            if "title" in data:
                note.title = data["title"]
            if "note" in data:
                note.note = data["note"]
            if "tags" in data:
                note.tags = data["tags"]

            session.commit()
            session.refresh(note)
            return note.to_dict()

    def delete_note(self, nid: str, user_id: str | None = None) -> bool:
        with self.get_session() as session:
            query = select(Note).where(Note.id == nid)
            if user_id:
                query = query.where(Note.user_id == user_id)
            note = session.execute(query).scalar_one_or_none()
            if not note:
                return False
            session.delete(note)
            session.commit()
            return True

    # ---------- Work Items ----------
    def list_work(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(WorkItem)
            if user_id:
                query = query.where(WorkItem.user_id == user_id)
            items = session.execute(query).scalars().all()
            return [w.to_dict() for w in items]

    def get_work(self, wid: str, user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(WorkItem).where(WorkItem.id == wid)
            if user_id:
                query = query.where(WorkItem.user_id == user_id)
            item = session.execute(query).scalar_one_or_none()
            return item.to_dict() if item else None

    def create_work(self, data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        self._validate_work(data)
        with self.get_session() as session:
            self.get_or_create_user(user_id)
            item = WorkItem(
                user_id=user_id,
                name=data["name"],
                start_date=data["start_date"],
                end_date=data.get("end_date"),
                description=data.get("description"),
                why=data.get("why"),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item.to_dict()

    def update_work(self, wid: str, data: Dict[str, Any], user_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(WorkItem).where(WorkItem.id == wid)
            if user_id:
                query = query.where(WorkItem.user_id == user_id)
            item = session.execute(query).scalar_one_or_none()
            if not item:
                return None

            merged = item.to_dict()
            merged.update({k: v for k, v in data.items() if v is not None})
            self._validate_work(merged, for_update=True)

            if "name" in data:
                item.name = data["name"]
            if "start_date" in data:
                item.start_date = data["start_date"]
            if "end_date" in data:
                item.end_date = data["end_date"]
            if "description" in data:
                item.description = data["description"]
            if "why" in data:
                item.why = data["why"]

            session.commit()
            session.refresh(item)
            return item.to_dict()

    def delete_work(self, wid: str, user_id: str | None = None) -> bool:
        with self.get_session() as session:
            query = select(WorkItem).where(WorkItem.id == wid)
            if user_id:
                query = query.where(WorkItem.user_id == user_id)
            item = session.execute(query).scalar_one_or_none()
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True
