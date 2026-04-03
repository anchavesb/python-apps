"""Tests for _extract_tool_calls_from_text — parsing tool calls from LLM text output."""

from dolores_assistant.pipeline import _extract_tool_calls_from_text


class TestExtractToolCallsFromText:
    """Test parsing tool calls that models output as JSON text."""

    def test_wrapped_tool_calls(self):
        """Model outputs {"tool_calls": [...]} wrapper."""
        text = '{"tool_calls": [{"id": "call_1234", "type": "function", "function": {"name": "todo_list_todos"}}]}'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "todo_list_todos"

    def test_direct_list(self):
        """Model outputs a bare list of tool calls."""
        text = '[{"id": "call_1", "type": "function", "function": {"name": "note_create_note", "arguments": "{\\"title\\": \\"test\\"}"}}]'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "note_create_note"
        assert result[0]["function"]["arguments"] == '{"title": "test"}'

    def test_multiple_tool_calls(self):
        """Multiple tool calls in one response."""
        text = '{"tool_calls": [{"id": "1", "type": "function", "function": {"name": "todo_list_todos"}}, {"id": "2", "type": "function", "function": {"name": "todo_create_todo", "arguments": "{\\"title\\": \\"buy milk\\"}"}}]}'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 2
        assert result[0]["function"]["name"] == "todo_list_todos"
        assert result[1]["function"]["name"] == "todo_create_todo"

    def test_missing_arguments_defaults_to_empty(self):
        """Tool call without arguments gets default empty JSON."""
        text = '{"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "todo_list_todos"}}]}'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert result[0]["function"]["arguments"] == "{}"

    def test_missing_id_gets_default(self):
        """Tool call without id gets a default."""
        text = '[{"type": "function", "function": {"name": "todo_list_todos"}}]'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert result[0]["id"] == "call_parsed"

    def test_plain_text_returns_none(self):
        """Normal text message should not be parsed."""
        assert _extract_tool_calls_from_text("Hello, how are you?") is None

    def test_empty_string_returns_none(self):
        assert _extract_tool_calls_from_text("") is None

    def test_invalid_json_returns_none(self):
        assert _extract_tool_calls_from_text("{not valid json}") is None

    def test_json_without_tool_calls_returns_none(self):
        """Valid JSON but not tool calls."""
        assert _extract_tool_calls_from_text('{"message": "hello"}') is None

    def test_empty_tool_calls_list_returns_none(self):
        assert _extract_tool_calls_from_text('{"tool_calls": []}') is None

    def test_list_without_function_name_returns_none(self):
        """List items missing function.name should be skipped."""
        assert _extract_tool_calls_from_text('[{"id": "1", "function": {}}]') is None

    def test_whitespace_padded_json(self):
        """JSON with leading/trailing whitespace."""
        text = '  {"tool_calls": [{"id": "1", "type": "function", "function": {"name": "todo_list_todos"}}]}  '
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert result[0]["function"]["name"] == "todo_list_todos"

    def test_arguments_as_dict(self):
        """Arguments already a dict (not a string) — should be preserved."""
        text = '{"tool_calls": [{"id": "1", "type": "function", "function": {"name": "note_create_note", "arguments": {"title": "test"}}}]}'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        # arguments can be dict or string — both should be accepted
        assert result[0]["function"]["name"] == "note_create_note"

    def test_single_dict_without_function_wrapper(self):
        """Model outputs {"name": "...", "arguments": {...}} directly."""
        text = '{"name": "todo_list_todos", "arguments": {}}'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "todo_list_todos"

    def test_trailing_model_tags_stripped(self):
        """Model appends <|python_tag|> or <|eot_id|> after JSON."""
        text = '{"name": "todo_list_todos", "arguments": {}}<|python_tag|>'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert result[0]["function"]["name"] == "todo_list_todos"

    def test_list_without_function_wrapper(self):
        """List of dicts with name/arguments at top level (no function key)."""
        text = '[{"name": "todo_create_todo", "arguments": {"title": "buy milk"}}]'
        result = _extract_tool_calls_from_text(text)
        assert result is not None
        assert result[0]["function"]["name"] == "todo_create_todo"
        assert result[0]["function"]["arguments"] == {"title": "buy milk"}
