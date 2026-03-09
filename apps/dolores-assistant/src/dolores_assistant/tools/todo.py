"""Todo tools: list, list today, create todos via the Todo app API."""

from __future__ import annotations

import json
from datetime import date

import httpx

from dolores_common.logging import get_logger

from ..config import settings
from .base import Tool

log = get_logger(__name__)


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if settings.todo_service_key:
        h["X-Service-Key"] = settings.todo_service_key
    return h


def _base_url() -> str:
    return f"{settings.todo_url}/api"


class ListTodosTool(Tool):
    @property
    def name(self) -> str:
        return "list_todos"

    @property
    def description(self) -> str:
        return "List the user's todos. Can filter by open/done status."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["open", "done", "all"],
                    "description": "Filter by status: 'open' (not done), 'done', or 'all'. Defaults to 'open'.",
                },
            },
            "required": [],
        }

    async def execute(self, status: str = "open", **kwargs) -> str:
        try:
            async with httpx.AsyncClient(headers=_headers(), timeout=10) as client:
                resp = await client.get(f"{_base_url()}/todos")
                resp.raise_for_status()
                todos = resp.json()
        except Exception as e:
            log.error("list_todos_failed", error=str(e))
            return f"Error fetching todos: {e}"

        if status == "open":
            todos = [t for t in todos if not t.get("done")]
        elif status == "done":
            todos = [t for t in todos if t.get("done")]

        if not todos:
            return "No todos found."

        lines = []
        for t in todos:
            done = "done" if t.get("done") else "open"
            due = f" (due: {t['due_date']})" if t.get("due_date") else ""
            priority = t.get("tags", {}).get("priority", "")
            priority_str = f" [{priority}]" if priority else ""
            lines.append(f"- {t['title']}{priority_str}{due} ({done})")
        return "\n".join(lines)


class ListTodosTodayTool(Tool):
    @property
    def name(self) -> str:
        return "list_todos_today"

    @property
    def description(self) -> str:
        return "List todos that are due today."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> str:
        try:
            async with httpx.AsyncClient(headers=_headers(), timeout=10) as client:
                resp = await client.get(f"{_base_url()}/todos")
                resp.raise_for_status()
                todos = resp.json()
        except Exception as e:
            log.error("list_todos_today_failed", error=str(e))
            return f"Error fetching todos: {e}"

        today = date.today().isoformat()
        today_todos = [t for t in todos if t.get("due_date") == today and not t.get("done")]

        if not today_todos:
            return "No todos due today."

        lines = []
        for t in today_todos:
            priority = t.get("tags", {}).get("priority", "")
            priority_str = f" [{priority}]" if priority else ""
            lines.append(f"- {t['title']}{priority_str}")
        return "\n".join(lines)


class CreateTodoTool(Tool):
    @property
    def name(self) -> str:
        return "create_todo"

    @property
    def description(self) -> str:
        return "Create a new todo item."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The todo title (required).",
                },
                "description": {
                    "type": "string",
                    "description": "Optional detailed description.",
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format (optional).",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level. Defaults to 'medium'.",
                },
                "category": {
                    "type": "string",
                    "description": "Category tag. Defaults to 'general'.",
                },
            },
            "required": ["title"],
        }

    async def execute(
        self,
        title: str,
        description: str = "",
        due_date: str = "",
        priority: str = "medium",
        category: str = "general",
        **kwargs,
    ) -> str:
        body: dict = {
            "title": title,
            "tags": {"category": category, "priority": priority},
        }
        if description:
            body["description"] = description
        if due_date:
            body["due_date"] = due_date

        try:
            async with httpx.AsyncClient(headers=_headers(), timeout=10) as client:
                resp = await client.post(f"{_base_url()}/todos", json=body)
                resp.raise_for_status()
                todo = resp.json()
        except httpx.HTTPStatusError as e:
            detail = e.response.text
            log.error("create_todo_failed", status=e.response.status_code, detail=detail)
            return f"Failed to create todo: {detail}"
        except Exception as e:
            log.error("create_todo_failed", error=str(e))
            return f"Error creating todo: {e}"

        due = f", due {todo.get('due_date')}" if todo.get("due_date") else ""
        return f"Created todo: \"{todo['title']}\"{due}"
