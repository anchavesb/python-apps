"""Tests for review_bot.llm_client and config._resolve_api_key."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from review_bot.config import _resolve_api_key
from review_bot.llm_client import retry_with_backoff


class TestResolveApiKey:
    def test_gemini_shared_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini-key")
        monkeypatch.delenv("REPO_OWNER_REPO_GEMINI_API_KEY", raising=False)

        key = _resolve_api_key("gemini/gemini-2.0-flash", "owner/repo")

        assert key == "shared-gemini-key"

    def test_anthropic_shared_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "shared-anthropic-key")
        monkeypatch.delenv("REPO_OWNER_REPO_ANTHROPIC_API_KEY", raising=False)

        key = _resolve_api_key("anthropic/claude-sonnet-4-20250514", "owner/repo")

        assert key == "shared-anthropic-key"

    def test_per_repo_gemini_override_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini-key")
        monkeypatch.setenv("REPO_OWNER_MYREPO_GEMINI_API_KEY", "per-repo-gemini-key")

        key = _resolve_api_key("gemini/gemini-2.0-flash", "owner/myrepo")

        assert key == "per-repo-gemini-key"

    def test_per_repo_anthropic_override_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "shared-anthropic-key")
        monkeypatch.setenv("REPO_OWNER_MYREPO_ANTHROPIC_API_KEY", "per-repo-anthropic-key")

        key = _resolve_api_key("anthropic/claude-sonnet-4-20250514", "owner/myrepo")

        assert key == "per-repo-anthropic-key"

    def test_safe_name_replaces_slash_and_hyphen(self, monkeypatch):
        monkeypatch.setenv("REPO_MY_ORG_MY_REPO_GEMINI_API_KEY", "org-repo-key")

        key = _resolve_api_key("gemini/gemini-2.0-flash", "my-org/my-repo")

        assert key == "org-repo-key"


class TestRetryWithBackoff:
    @pytest.mark.anyio
    async def test_successful_call_no_retries(self):
        mock_func = AsyncMock(return_value="success")
        decorated = retry_with_backoff(max_retries=3, initial_delay=0.01)(mock_func)

        result = await decorated()

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.anyio
    async def test_retry_on_429_then_success(self):
        mock_func = AsyncMock()
        mock_func.side_effect = [
            Exception("Rate limit reached (429)"),
            "success",
        ]
        decorated = retry_with_backoff(max_retries=3, initial_delay=0.01)(mock_func)

        result = await decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.anyio
    async def test_final_failure_after_retries(self):
        mock_func = AsyncMock()
        mock_func.side_effect = Exception("Rate limit reached (429)")
        decorated = retry_with_backoff(max_retries=2, initial_delay=0.01)(mock_func)

        with pytest.raises(Exception, match="429"):
            await decorated()

        assert mock_func.call_count == 3  # Initial attempt + 2 retries

    @pytest.mark.anyio
    async def test_no_retry_on_non_retryable_error(self):
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Invalid argument")
        decorated = retry_with_backoff(max_retries=3, initial_delay=0.01)(mock_func)

        with pytest.raises(ValueError, match="Invalid argument"):
            await decorated()

        assert mock_func.call_count == 1

    @pytest.mark.anyio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_exponential_backoff_delay(self, mock_sleep):
        mock_func = AsyncMock()
        mock_func.side_effect = [
            Exception("429 error"),
            Exception("429 error"),
            "success",
        ]
        # initial=1.0, factor=2.0 -> delays should be 1.0, 2.0
        decorated = retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0)(mock_func)

        await decorated()

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)
