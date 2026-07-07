"""PostgreSQL storage backend with multiuser support."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Note, RssFeed, RssItemState, Todo, User
from .storage import PRIORITIES, ValidationError


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

    # ---------- User Management ----------
    def find_user_by_email(self, email: str | None) -> User | None:
        """Look up a user by email address."""
        if not email:
            return None
        with self.get_session() as session:
            return session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()

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
    def list_todos(self, user_id: str | None = None, done: bool | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(Todo)
            if user_id:
                query = query.where(Todo.user_id == user_id)
            if done is not None:
                query = query.where(Todo.done == done)
            # Sort by due_date ascending (nulls last), then created_at descending
            query = query.order_by(Todo.due_date.asc().nullslast(), Todo.created_at.desc())
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

    # ---------- RSS Feeds ----------
    def list_rss_feeds(self, user_id: str | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(RssFeed)
            if user_id:
                query = query.where(RssFeed.user_id == user_id)
            feeds = session.execute(query).scalars().all()
            return [f.to_dict() for f in feeds]

    def create_rss_feed(self, data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        with self.get_session() as session:
            self.get_or_create_user(user_id)
            feed = RssFeed(
                user_id=user_id,
                url=data["url"],
                title=data.get("title", "Unnamed Feed"),
            )
            session.add(feed)
            session.commit()
            session.refresh(feed)
            return feed.to_dict()

    def delete_rss_feed(self, feed_id: str, user_id: str | None = None) -> bool:
        with self.get_session() as session:
            query = select(RssFeed).where(RssFeed.id == feed_id)
            if user_id:
                query = query.where(RssFeed.user_id == user_id)
            feed = session.execute(query).scalar_one_or_none()
            if not feed:
                return False
            session.delete(feed)
            session.commit()
            return True

    # ---------- RSS Item States ----------
    def get_rss_item_states(self, user_id: str | None = None, feed_id: str | None = None) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            query = select(RssItemState)
            if user_id:
                query = query.where(RssItemState.user_id == user_id)
            if feed_id:
                query = query.where(RssItemState.feed_id == feed_id)
            states = session.execute(query).scalars().all()
            return [s.to_dict() for s in states]

    def update_rss_item_state(self, user_id: str, feed_id: str, item_guid: str, read: bool | None = None, starred: bool | None = None) -> Dict[str, Any]:
        with self.get_session() as session:
            self.get_or_create_user(user_id)
            query = select(RssItemState).where(
                RssItemState.user_id == user_id,
                RssItemState.feed_id == feed_id,
                RssItemState.item_guid == item_guid
            )
            state = session.execute(query).scalar_one_or_none()

            if not state:
                state = RssItemState(
                    user_id=user_id,
                    feed_id=feed_id,
                    item_guid=item_guid,
                    read=False,
                    starred=False,
                )
                session.add(state)

            if read is not None:
                state.read = read
            if starred is not None:
                state.starred = starred

            session.commit()
            session.refresh(state)

            # If both read and starred are False, clean it up to save space
            if not state.read and not state.starred:
                session.delete(state)
                session.commit()
                return {
                    "id": state.id,
                    "feed_id": feed_id,
                    "item_guid": item_guid,
                    "read": False,
                    "starred": False,
                }

            return state.to_dict()

    def mark_all_rss_items_read(self, user_id: str, feed_id: str, item_guids: List[str]):
        for guid in item_guids:
            self.update_rss_item_state(user_id, feed_id, guid, read=True)
