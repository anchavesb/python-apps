"""Tests for llm_client.py — API key resolution and LLM call behavior."""

from __future__ import annotations

import pytest

from review_bot.llm_client import resolve_api_key


class TestResolveApiKey:
    def test_gemini_shared_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini-key")
        monkeypatch.delenv("REPO_OWNER_REPO_GEMINI_API_KEY", raising=False)

        key = resolve_api_key("gemini/gemini-2.0-flash", "owner/repo")

        assert key == "shared-gemini-key"

    def test_anthropic_shared_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "shared-anthropic-key")
        monkeypatch.delenv("REPO_OWNER_REPO_ANTHROPIC_API_KEY", raising=False)

        key = resolve_api_key("anthropic/claude-sonnet-4-20250514", "owner/repo")

        assert key == "shared-anthropic-key"

    def test_per_repo_gemini_override_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini-key")
        monkeypatch.setenv("REPO_OWNER_MYREPO_GEMINI_API_KEY", "per-repo-gemini-key")

        key = resolve_api_key("gemini/gemini-2.0-flash", "owner/myrepo")

        assert key == "per-repo-gemini-key"

    def test_per_repo_anthropic_override_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "shared-anthropic-key")
        monkeypatch.setenv("REPO_OWNER_MYREPO_ANTHROPIC_API_KEY", "per-repo-anthropic-key")

        key = resolve_api_key("anthropic/claude-sonnet-4-20250514", "owner/myrepo")

        assert key == "per-repo-anthropic-key"

    def test_safe_name_replaces_slash_and_hyphen(self, monkeypatch):
        monkeypatch.setenv("REPO_MY_ORG_MY_REPO_GEMINI_API_KEY", "org-repo-key")

        key = resolve_api_key("gemini/gemini-2.0-flash", "my-org/my-repo")

        assert key == "org-repo-key"

    def test_missing_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("REPO_OWNER_REPO_GEMINI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            resolve_api_key("gemini/gemini-2.0-flash", "owner/repo")

    def test_missing_anthropic_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("REPO_OWNER_REPO_ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            resolve_api_key("anthropic/claude-sonnet-4-20250514", "owner/repo")
