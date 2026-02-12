"""SQLAlchemy models for the todo app with multiuser support."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # OIDC sub claim
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    todos: Mapped[list["Todo"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notes: Mapped[list["Note"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    due_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="todos")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": self.tags or {},
            "done": self.done,
            "due_date": self.due_date,
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.updated_at else None,
        }


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="notes")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "note": self.note,
            "tags": self.tags or {},
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.updated_at else None,
        }


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    start_date: Mapped[str] = mapped_column(String(32), nullable=False)
    end_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    why: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="work_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "description": self.description,
            "why": self.why,
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.updated_at else None,
        }
