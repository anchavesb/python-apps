"""Tests for tool registry filtering."""

import pytest

from dolores_assistant.tools import registry
from dolores_assistant.tools.base import Tool


class FakeTool(Tool):
    """Minimal tool for testing registry filtering."""

    def __init__(self, tool_name: str):
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake {self._name}"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "ok"


@pytest.fixture(autouse=True)
def _populate_tools():
    """Set up fake tools for each test, restore after."""
    original = registry.TOOLS[:]
    registry.TOOLS = [
        FakeTool("todo_list_todos"),
        FakeTool("todo_create_todo"),
        FakeTool("note_list_notes"),
        FakeTool("note_create_note"),
        FakeTool("work_log_hours"),
    ]
    yield
    registry.TOOLS = original


class TestGetToolDefinitions:
    def test_no_filter_returns_all(self):
        defs = registry.get_tool_definitions(None)
        assert len(defs) == 5

    def test_filter_todo(self):
        defs = registry.get_tool_definitions({"todo"})
        names = [d["function"]["name"] for d in defs]
        assert names == ["todo_list_todos", "todo_create_todo"]

    def test_filter_note(self):
        defs = registry.get_tool_definitions({"note"})
        names = [d["function"]["name"] for d in defs]
        assert names == ["note_list_notes", "note_create_note"]

    def test_filter_work(self):
        defs = registry.get_tool_definitions({"work"})
        names = [d["function"]["name"] for d in defs]
        assert names == ["work_log_hours"]

    def test_filter_no_match_returns_empty(self):
        defs = registry.get_tool_definitions({"calendar"})
        assert defs == []

    def test_filter_multiple_substrings(self):
        defs = registry.get_tool_definitions({"todo", "note"})
        names = [d["function"]["name"] for d in defs]
        assert len(names) == 4
        assert "work_log_hours" not in names

    def test_openai_format(self):
        defs = registry.get_tool_definitions({"todo"})
        for d in defs:
            assert d["type"] == "function"
            assert "name" in d["function"]
            assert "description" in d["function"]
            assert "parameters" in d["function"]


class TestGetToolByName:
    def test_found(self):
        tool = registry.get_tool_by_name("todo_list_todos")
        assert tool is not None
        assert tool.name == "todo_list_todos"

    def test_not_found(self):
        assert registry.get_tool_by_name("nonexistent") is None
