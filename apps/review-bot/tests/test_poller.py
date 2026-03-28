"""Tests for poller.py — SHA comparison logic, per-repo error isolation, dispatch."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from review_bot.config import RegistryError, RepoEntry
from review_bot.poller import _poll_repo
from review_bot.schemas import PRInfo

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_entry(repo: str = "owner/repo") -> RepoEntry:
    return RepoEntry(repo=repo)


def _pr(number: int, head_sha: str) -> PRInfo:
    owner, repo = ("owner", "repo")
    return PRInfo(number=number, head_sha=head_sha, title=f"PR {number}", owner=owner, repo=repo)


def _make_effective(token: str = "gh-token") -> MagicMock:
    eff = MagicMock()
    eff.github_token = token
    return eff


# ---------------------------------------------------------------------------
# _poll_repo — SHA comparison dispatch
# ---------------------------------------------------------------------------


@patch("review_bot.poller.run_review", new_callable=AsyncMock)
@patch("review_bot.poller.resolve_effective_config")
@patch("review_bot.poller.list_open_prs")
async def test_new_pr_triggers_full_diff(mock_list_prs, mock_resolve, mock_run_review):
    """stored_sha is None → diff_type='full', before_sha=None."""
    effective = _make_effective()
    mock_resolve.return_value = effective

    mock_list_prs.return_value = [_pr(1, "abc")]

    store = AsyncMock()
    store.get_sha = AsyncMock(return_value=None)

    config = MagicMock()

    await _poll_repo(_repo_entry(), store, config)

    mock_run_review.assert_called_once_with(
        repo="owner/repo",
        pr_number=1,
        head_sha="abc",
        diff_type="full",
        before_sha=None,
    )


@patch("review_bot.poller.run_review", new_callable=AsyncMock)
@patch("review_bot.poller.resolve_effective_config")
@patch("review_bot.poller.list_open_prs")
async def test_updated_pr_triggers_incremental_diff_with_correct_shas(mock_list_prs, mock_resolve, mock_run_review):
    """stored_sha != head_sha → diff_type='incremental', before_sha=stored_sha."""
    effective = _make_effective()
    mock_resolve.return_value = effective

    mock_list_prs.return_value = [_pr(2, "new-sha")]

    store = AsyncMock()
    store.get_sha = AsyncMock(return_value="old-sha")

    config = MagicMock()

    await _poll_repo(_repo_entry(), store, config)

    mock_run_review.assert_called_once_with(
        repo="owner/repo",
        pr_number=2,
        head_sha="new-sha",
        diff_type="incremental",
        before_sha="old-sha",
    )


@patch("review_bot.poller.run_review", new_callable=AsyncMock)
@patch("review_bot.poller.resolve_effective_config")
@patch("review_bot.poller.list_open_prs")
async def test_unchanged_pr_is_skipped(mock_list_prs, mock_resolve, mock_run_review):
    """stored_sha == head_sha → no diff fetched, no review posted."""
    effective = _make_effective()
    mock_resolve.return_value = effective

    mock_list_prs.return_value = [_pr(3, "same-sha")]

    store = AsyncMock()
    store.get_sha = AsyncMock(return_value="same-sha")

    config = MagicMock()

    await _poll_repo(_repo_entry(), store, config)

    mock_run_review.assert_not_called()


@patch("review_bot.poller.run_review", new_callable=AsyncMock)
@patch("review_bot.poller.resolve_effective_config")
@patch("review_bot.poller.list_open_prs")
async def test_unregistered_repo_is_logged_and_not_polled(mock_list_prs, mock_resolve, mock_run_review):
    """resolve_effective_config raises RegistryError; it's logged and repo skiped."""
    mock_resolve.side_effect = RegistryError("not registered")

    store = AsyncMock()
    config = MagicMock()

    # Should NOT raise anymore, but log and return
    await _poll_repo(_repo_entry("unknown/repo"), store, config)

    mock_run_review.assert_not_called()


@patch("review_bot.poller.run_review", new_callable=AsyncMock)
@patch("review_bot.poller.resolve_effective_config")
@patch("review_bot.poller.list_open_prs")
async def test_llm_failure_is_logged_and_does_not_call_set_sha(mock_list_prs, mock_resolve, mock_run_review):
    """run_review raising means error is logged but SHA update never happens."""
    effective = _make_effective()
    mock_resolve.return_value = effective

    mock_list_prs.return_value = [_pr(4, "head")]

    store = AsyncMock()
    store.get_sha = AsyncMock(return_value=None)

    mock_run_review.side_effect = RuntimeError("LLM down")

    config = MagicMock()

    # Should NOT raise anymore because of return_exceptions=True
    await _poll_repo(_repo_entry(), store, config)

    store.set_sha.assert_not_called()


# ---------------------------------------------------------------------------
# run_polling_loop — per-repo isolation
# ---------------------------------------------------------------------------


@patch("review_bot.poller._poll_repo", new_callable=AsyncMock)
@patch("review_bot.poller.get_registry")
@patch("review_bot.poller.get_settings")
@patch("review_bot.poller.get_state_store")
async def test_one_repo_exception_does_not_block_other_repos(
    mock_get_store, mock_get_settings, mock_get_registry, mock_poll_repo
):
    """An exception on one repo must not prevent other repos from being polled."""
    from review_bot.poller import run_polling_loop

    settings = MagicMock()
    settings.poll_interval_seconds = 0
    mock_get_settings.return_value = settings

    repo_a = RepoEntry(repo="owner/repo-a")
    repo_b = RepoEntry(repo="owner/repo-b")
    registry = MagicMock()
    registry.repositories = [repo_a, repo_b]
    mock_get_registry.return_value = registry

    mock_get_store.return_value = AsyncMock()

    call_count = 0

    async def _side_effect(repo_entry, store, config):
        nonlocal call_count
        call_count += 1
        if repo_entry.repo == "owner/repo-a":
            raise RuntimeError("repo-a failed")

    mock_poll_repo.side_effect = _side_effect

    # Run one cycle then cancel
    task = asyncio.create_task(run_polling_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Both repos must have been attempted despite repo-a raising
    assert call_count >= 2
    repos_polled = [call.args[0].repo for call in mock_poll_repo.call_args_list]
    assert "owner/repo-a" in repos_polled
    assert "owner/repo-b" in repos_polled


# ---------------------------------------------------------------------------
# Integration: full pipeline with respx-mocked GitHub HTTP API
# ---------------------------------------------------------------------------


class TestPollerIntegration:
    """End-to-end: respx-mocked GitHub HTTP API + real in-memory StateStore + patched LiteLLM.

    Exercises the complete polling pipeline — SHA comparison, full diff fetch,
    AGENTS.md discovery, prompt assembly, LLM call, review parsing, and review
    posting — without mocking any application logic layer.
    """

    @pytest.fixture(autouse=True)
    def _setup_singletons(self, monkeypatch):
        import review_bot.config as cfg
        import review_bot.prompt as pm
        import review_bot.review_runner as rr

        monkeypatch.setattr(
            cfg,
            "_registry",
            cfg.RepoRegistry(
                defaults={"model": "gemini/flash"},
                repositories=[cfg.RepoEntry(repo="owner/repo")],
            ),
        )
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("GITHUB_TOKEN", "test-gh-token")
        monkeypatch.setattr(pm, "_base_prompt", "Review this PR carefully.")
        rr.init_semaphore(3)

    @pytest.fixture
    async def real_store(self):
        from review_bot.state_store import StateStore, set_state_store

        store = StateStore(":memory:")
        await store.init()
        set_state_store(store)
        yield store
        await store.close()

    async def test_new_pr_posts_review_with_attribution_and_stores_sha(self, real_store):
        """New PR triggers full diff, LLM response assembled into review, posted with attribution, SHA stored."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx
        import respx

        from review_bot.config import RepoEntry
        from review_bot.github_client import set_github_client
        from review_bot.poller import _poll_repo

        REPO = "owner/repo"
        PR_NUMBER = 1
        HEAD_SHA = "abc123"
        # Adds three new lines to src/foo.py; changed_lines will be [1, 2, 3]
        PATCH_TEXT = "@@ -0,0 +1,3 @@\n+line1\n+line2\n+line3"

        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = json.dumps(
            {
                "summary": "Looks good",
                "comments": [{"path": "src/foo.py", "line": 1, "body": "Nice change"}],
            }
        )

        with respx.mock(assert_all_called=False) as github_mock:
            github_mock.get("https://api.github.com/repos/owner/repo/pulls").mock(
                return_value=httpx.Response(
                    200,
                    json=[{"number": PR_NUMBER, "head": {"sha": HEAD_SHA}, "title": "Test PR"}],
                )
            )
            github_mock.get("https://api.github.com/repos/owner/repo/pulls/1/files").mock(
                return_value=httpx.Response(
                    200,
                    json=[{"filename": "src/foo.py", "patch": PATCH_TEXT}],
                )
            )
            # AGENTS.md not present at root (src/foo.py has only one dir level,
            # so no subdir AGENTS.md candidate is generated under the two-component
            # prefix logic)
            github_mock.get("https://api.github.com/repos/owner/repo/contents/AGENTS.md").mock(
                return_value=httpx.Response(404)
            )
            # per-repo .github/review-bot.yml not present
            github_mock.get("https://api.github.com/repos/owner/repo/contents/.github/review-bot.yml").mock(
                return_value=httpx.Response(404)
            )
            review_route = github_mock.post("https://api.github.com/repos/owner/repo/pulls/1/reviews").mock(
                return_value=httpx.Response(200, json={"id": 1})
            )

            async with httpx.AsyncClient() as http_client:
                # Wire the real httpx client so module-level functions (fetch_file_contents,
                # post_review, etc.) use it — respx intercepts its transport.
                set_github_client(http_client)

                with patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_response):
                    await _poll_repo(RepoEntry(repo=REPO), real_store, MagicMock())

        assert review_route.called, "Expected review to be posted to GitHub Reviews API"
        posted = json.loads(review_route.calls.last.request.content)

        # Summary must carry attribution prefix and original LLM summary text
        assert "> Automated review by review-bot | Model: gemini/flash" in posted["body"]
        assert "Looks good" in posted["body"]

        # Inline comment on a valid changed line must be posted with attribution
        assert len(posted["comments"]) == 1
        comment = posted["comments"][0]
        assert comment["path"] == "src/foo.py"
        assert comment["line"] == 1
        assert "> Automated review by review-bot | Model: gemini/flash" in comment["body"]
        assert "Nice change" in comment["body"]

        # State store must be updated with the new head SHA
        stored = await real_store.get_sha(REPO, PR_NUMBER)
        assert stored == HEAD_SHA
