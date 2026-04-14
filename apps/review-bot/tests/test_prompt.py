"""Tests for prompt.py — layered prompt assembly."""

from __future__ import annotations

import pytest

import review_bot.prompt as prompt_module
from review_bot.prompt import assemble_prompt, load_base_prompt
from review_bot.schemas import AgentsFile, DiffFile, DiffMetadata, EffectiveConfig

BASE_PROMPT_TEXT = "You are a PR reviewer. Return JSON with summary and comments."


def _make_config(
    prompt_mode: str = "base",
    prompt_extension: str | None = None,
) -> EffectiveConfig:
    return EffectiveConfig(
        repo="owner/repo",
        model="gemini/gemini-2.0-flash",
        prompt_mode=prompt_mode,
        prompt_extension=prompt_extension,
        api_key="test-key",
        github_token="test-token",
    )


def _make_meta(files: dict[str, str | None] | None = None) -> DiffMetadata:
    if files is None:
        return DiffMetadata(files={})
    return DiffMetadata(
        files={path: DiffFile(path=path, changed_lines=[], content=content) for path, content in files.items()}
    )


@pytest.fixture(autouse=True)
def reset_base_prompt():
    original = prompt_module._base_prompt
    prompt_module._base_prompt = BASE_PROMPT_TEXT
    yield
    prompt_module._base_prompt = original


class TestAssemblePromptBaseMode:
    def test_base_mode_system_message_contains_base_prompt(self):
        config = _make_config(prompt_mode="base")
        messages = assemble_prompt(config, [], "diff text here", _make_meta())

        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == BASE_PROMPT_TEXT

    def test_base_mode_user_message_contains_diff(self):
        config = _make_config(prompt_mode="base")
        messages = assemble_prompt(config, [], "diff text here", _make_meta())

        user_msg = next(m for m in messages if m["role"] == "user")
        assert "diff text here" in user_msg["content"]

    def test_base_mode_no_agents_section_when_empty(self):
        config = _make_config(prompt_mode="base")
        messages = assemble_prompt(config, [], "diff text here", _make_meta())

        user_msg = next(m for m in messages if m["role"] == "user")
        assert "AGENTS.md" not in user_msg["content"]

    def test_user_message_contains_full_file_context(self):
        config = _make_config(prompt_mode="base")
        meta = _make_meta({"src/foo.py": "def foo(): pass"})
        messages = assemble_prompt(config, [], "diff text here", meta)

        user_msg = next(m for m in messages if m["role"] == "user")
        assert "# Full File Context" in user_msg["content"]
        assert "File: src/foo.py" in user_msg["content"]
        assert "def foo(): pass" in user_msg["content"]


class TestAssemblePromptWithAgentsMd:
    def test_agents_content_appears_in_user_message(self):
        config = _make_config(prompt_mode="base")
        agents = [AgentsFile(path="AGENTS.md", content="Follow PEP 8.")]
        messages = assemble_prompt(config, agents, "diff text", _make_meta())

        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Follow PEP 8." in user_msg["content"]

    def test_agents_block_appears_before_diff(self):
        config = _make_config(prompt_mode="base")
        agents = [AgentsFile(path="AGENTS.md", content="Guideline text")]
        messages = assemble_prompt(config, agents, "diff text", _make_meta())

        user_content = next(m for m in messages if m["role"] == "user")["content"]
        assert user_content.index("Guideline text") < user_content.index("diff text")

    def test_agents_source_path_header_present(self):
        config = _make_config(prompt_mode="base")
        agents = [AgentsFile(path="apps/AGENTS.md", content="App guideline")]
        messages = assemble_prompt(config, agents, "diff text", _make_meta())

        user_content = next(m for m in messages if m["role"] == "user")["content"]
        assert "apps/AGENTS.md" in user_content


class TestExtendMode:
    def test_extend_mode_appends_extension_to_base_prompt(self):
        config = _make_config(prompt_mode="extend", prompt_extension="Focus on type safety.")
        messages = assemble_prompt(config, [], "diff text", _make_meta())

        system_content = next(m for m in messages if m["role"] == "system")["content"]
        assert BASE_PROMPT_TEXT in system_content
        assert "Focus on type safety." in system_content

    def test_extend_mode_extension_follows_base_prompt(self):
        config = _make_config(prompt_mode="extend", prompt_extension="Extra instructions.")
        messages = assemble_prompt(config, [], "diff text", _make_meta())

        system_content = next(m for m in messages if m["role"] == "system")["content"]
        assert system_content.index(BASE_PROMPT_TEXT) < system_content.index("Extra instructions.")


class TestReplaceMode:
    def test_replace_mode_uses_extension_as_active_prompt(self):
        config = _make_config(prompt_mode="replace", prompt_extension="Custom prompt only.")
        messages = assemble_prompt(config, [], "diff text", _make_meta())

        system_content = next(m for m in messages if m["role"] == "system")["content"]
        assert system_content == "Custom prompt only."

    def test_replace_mode_excludes_base_prompt(self):
        config = _make_config(prompt_mode="replace", prompt_extension="Custom prompt only.")
        messages = assemble_prompt(config, [], "diff text", _make_meta())

        system_content = next(m for m in messages if m["role"] == "system")["content"]
        assert BASE_PROMPT_TEXT not in system_content

    def test_replace_mode_returns_two_messages(self):
        config = _make_config(prompt_mode="replace", prompt_extension="Custom prompt.")
        messages = assemble_prompt(config, [], "diff text", _make_meta())

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestLoadBasePrompt:
    def test_load_base_prompt_reads_file_and_stores_module_level(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base_review.md").write_text("Loaded prompt content.")

        result = load_base_prompt(str(prompts_dir))

        assert result == "Loaded prompt content."
        assert prompt_module._base_prompt == "Loaded prompt content."
