"""Tests for agents_discovery.py — AGENTS.md discovery via GitHub Contents API."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from review_bot.agents_discovery import discover_agents_md
from review_bot.schemas import AgentsFile


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.new_event_loop().run_until_complete(coro)


class TestDiscoverAgentsMd:
    def test_root_only_when_subdir_agents_md_not_found(self):
        root_content = "# Root AGENTS\nDo the right thing."

        async def fake_fetch(owner, repo, path, ref, token):
            if path == "AGENTS.md":
                return root_content
            return None  # src/AGENTS.md does not exist

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            result = run(discover_agents_md("owner", "repo", ["src/foo.py", "src/bar.py"], "abc123", "token"))

        assert len(result) == 1
        assert result[0] == AgentsFile(path="AGENTS.md", content=root_content)

    def test_root_and_subdir_both_included(self):
        root_content = "root content"
        apps_brain_content = "apps/dolores-brain subdir content"

        async def fake_fetch(owner, repo, path, ref, token):
            if path == "AGENTS.md":
                return root_content
            if path == "apps/dolores-brain/AGENTS.md":
                return apps_brain_content
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            result = run(
                discover_agents_md(
                    "owner",
                    "repo",
                    ["apps/dolores-brain/src/foo.py", "apps/dolores-brain/src/bar.py"],
                    "abc123",
                    "token",
                )
            )

        assert len(result) == 2
        assert result[0] == AgentsFile(path="AGENTS.md", content=root_content)
        assert result[1] == AgentsFile(path="apps/dolores-brain/AGENTS.md", content=apps_brain_content)

    def test_subdir_excluded_when_diff_does_not_touch_it(self):
        root_content = "root content"
        libs_fetch_called = []

        async def fake_fetch(owner, repo, path, ref, token):
            if path == "AGENTS.md":
                return root_content
            if path == "libs/AGENTS.md":
                libs_fetch_called.append(path)
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            result = run(discover_agents_md("owner", "repo", ["apps/foo.py"], "abc123", "token"))

        paths = [af.path for af in result]
        assert "AGENTS.md" in paths
        assert not libs_fetch_called, "libs/AGENTS.md should not be fetched"

    def test_returns_empty_list_when_no_agents_md_anywhere(self):
        with patch("review_bot.agents_discovery.fetch_file_contents", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            result = run(discover_agents_md("owner", "repo", ["src/main.py"], "abc123", "token"))

        assert result == []

    def test_root_first_in_return_order(self):
        async def fake_fetch(owner, repo, path, ref, token):
            if path == "AGENTS.md":
                return "root"
            if path == "apps/dolores-brain/AGENTS.md":
                return "apps/dolores-brain"
            if path == "libs/dolores-common/AGENTS.md":
                return "libs/dolores-common"
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            result = run(
                discover_agents_md(
                    "owner",
                    "repo",
                    ["apps/dolores-brain/src/a.py", "libs/dolores-common/src/b.py"],
                    "abc123",
                    "token",
                )
            )

        assert result[0].path == "AGENTS.md"
        assert all(af.path != "AGENTS.md" for af in result[1:])

    def test_no_subdir_prefix_for_root_level_files(self):
        """Files with no directory component do not add a prefix to the candidate set."""
        calls: list[str] = []

        async def fake_fetch(owner, repo, path, ref, token):
            calls.append(path)
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            run(discover_agents_md("owner", "repo", ["README.md", "setup.py"], "abc123", "token"))

        assert calls == ["AGENTS.md"]

    def test_two_component_prefix_used_for_deep_monorepo_paths(self):
        """Paths with three+ components (apps/app-name/src/...) produce a two-level prefix."""
        calls: list[str] = []

        async def fake_fetch(owner, repo, path, ref, token):
            calls.append(path)
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            run(
                discover_agents_md(
                    "owner",
                    "repo",
                    ["apps/review-bot/src/review_bot/routes.py"],
                    "abc123",
                    "token",
                )
            )

        assert "apps/review-bot/AGENTS.md" in calls
        # Must NOT look for the single-component prefix
        assert "apps/AGENTS.md" not in calls

    def test_single_level_paths_do_not_generate_subdir_candidate(self):
        """Paths with only one directory component (e.g. src/foo.py) do not trigger
        a subdir AGENTS.md lookup under the new two-component prefix logic."""
        calls: list[str] = []

        async def fake_fetch(owner, repo, path, ref, token):
            calls.append(path)
            return None

        with patch("review_bot.agents_discovery.fetch_file_contents", side_effect=fake_fetch):
            run(discover_agents_md("owner", "repo", ["src/main.py", "lib/utils.py"], "abc123", "token"))

        # Only the root AGENTS.md should be checked — no single-level subdir candidate.
        assert calls == ["AGENTS.md"]
