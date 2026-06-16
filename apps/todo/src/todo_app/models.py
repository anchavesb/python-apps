"""SQLAlchemy models for the todo app with multiuser support."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
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
    rss_feeds: Mapped[list["RssFeed"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    rss_item_states: Mapped[list["RssItemState"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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


class RssFeed(Base):
    __tablename__ = "rss_feeds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="rss_feeds")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.created_at else None,
        }


class RssItemState(Base):
    __tablename__ = "rss_item_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), nullable=False, index=True)
    feed_id: Mapped[str] = mapped_column(String(36), ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    item_guid: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="rss_item_states")
    feed: Mapped["RssFeed"] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feed_id": self.feed_id,
            "item_guid": self.item_guid,
            "read": self.read,
            "starred": self.starred,
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.updated_at else None,
        }
