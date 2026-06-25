"""Tests for review_runner.py — shared run_review() coroutine and semaphore management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import review_bot.review_runner as rr
from review_bot.review_runner import get_semaphore, init_semaphore, run_review
from review_bot.schemas import DiffFile, DiffMetadata, InlineComment, ReviewResult

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_diff_metadata(*paths: str) -> DiffMetadata:
    files = {p: DiffFile(path=p, changed_lines=[1, 2, 3]) for p in paths}
    return DiffMetadata(files=files)


def _make_review_result() -> ReviewResult:
    return ReviewResult(
        summary="Looks good",
        inline_comments=[InlineComment(path="src/foo.py", line=1, body="Nice")],
    )


@pytest.fixture(autouse=True)
def _reset_semaphore():
    """Ensure semaphore is initialized for each test and reset afterward."""
    original = rr._semaphore
    init_semaphore(3)
    yield
    rr._semaphore = original


# ---------------------------------------------------------------------------
# Semaphore management
# ---------------------------------------------------------------------------


def test_get_semaphore_raises_when_uninitialized():
    original = rr._semaphore
    rr._semaphore = None
    try:
        with pytest.raises(RuntimeError, match="Semaphore not initialized"):
            get_semaphore()
    finally:
        rr._semaphore = original


def test_init_semaphore_sets_correct_value():
    init_semaphore(5)
    sem = get_semaphore()
    assert sem._value == 5  # noqa: SLF001


# ---------------------------------------------------------------------------
# run_review — full diff
# ---------------------------------------------------------------------------


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_run_review_full_diff_calls_get_diff_with_correct_args(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff text", diff_meta)

    store = AsyncMock()
    store.get_sha = AsyncMock(return_value=None)
    store.set_sha = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    await run_review(
        repo="owner/repo",
        pr_number=42,
        head_sha="abc123",
        diff_type="full",
        before_sha=None,
    )

    mock_get_diff.assert_called_once_with(
        "owner",
        "repo",
        42,
        "full",
        before_sha=None,
        after_sha="abc123",
        token="tok",
    )


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_run_review_incremental_diff_passes_before_sha(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None

    diff_meta = _make_diff_metadata("src/bar.py")
    mock_get_diff.return_value = ("incremental diff", diff_meta)

    store = AsyncMock()
    store.set_sha = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    await run_review(
        repo="owner/repo",
        pr_number=7,
        head_sha="newsha",
        diff_type="incremental",
        before_sha="oldsha",
    )

    mock_get_diff.assert_called_once_with(
        "owner",
        "repo",
        7,
        "incremental",
        before_sha="oldsha",
        after_sha="newsha",
        token="tok",
    )


# ---------------------------------------------------------------------------
# run_review — set_sha called with correct head_sha after post_review
# ---------------------------------------------------------------------------


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_run_review_calls_set_sha_with_head_sha_after_post_review(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff", diff_meta)

    store = AsyncMock()
    store.set_state = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    call_order = []
    mock_post_review.side_effect = lambda *a, **kw: call_order.append("post_review")
    store.set_state.side_effect = lambda *a, **kw: call_order.append("set_state")

    await run_review(
        repo="owner/repo",
        pr_number=1,
        head_sha="headsha",
        diff_type="full",
        before_sha=None,
        last_comment_id=999,
    )

    store.set_state.assert_called_once_with("owner/repo", 1, "headsha", 999)
    assert call_order == ["post_review", "set_state"], "set_state must be called after post_review"


# ---------------------------------------------------------------------------
# run_review — semaphore released on completion and on exception
# ---------------------------------------------------------------------------


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_semaphore_released_after_successful_run(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff", diff_meta)

    store = AsyncMock()
    store.set_sha = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    sem = get_semaphore()
    await run_review(repo="owner/repo", pr_number=1, head_sha="sha", diff_type="full", before_sha=None)

    assert not sem.locked()


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
async def test_semaphore_released_after_exception(
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff", diff_meta)

    store = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.side_effect = RuntimeError("LLM exploded")

    sem = get_semaphore()
    with pytest.raises(RuntimeError, match="LLM exploded"):
        await run_review(repo="owner/repo", pr_number=2, head_sha="sha", diff_type="full", before_sha=None)

    assert not sem.locked()


# ---------------------------------------------------------------------------
# run_review — per-repo .github/review-bot.yml config fetch (Layer 1)
# ---------------------------------------------------------------------------


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_per_repo_yml_fetched_and_passed_to_resolve_effective_config(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    """run_review must fetch .github/review-bot.yml and pass it to resolve_effective_config."""
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective

    per_repo_content = "model: anthropic/claude-3-5-sonnet"
    mock_fetch_file.return_value = per_repo_content

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff", diff_meta)

    store = AsyncMock()
    store.set_sha = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    await run_review(repo="owner/repo", pr_number=1, head_sha="sha", diff_type="full", before_sha=None)

    # fetch_file_contents must be called for the per-repo config path
    mock_fetch_file.assert_called_once_with("owner", "repo", ".github/review-bot.yml", "HEAD", "tok")

    # resolve_effective_config must be called a second time with the fetched content
    calls = mock_resolve.call_args_list
    assert any(
        call.args == ("owner/repo", per_repo_content) or call.kwargs.get("per_repo_yml_content") == per_repo_content
        for call in calls
    ), "resolve_effective_config must be called with the per-repo yml content"


@patch("review_bot.review_runner.resolve_effective_config")
@patch("review_bot.review_runner.get_diff", new_callable=AsyncMock)
@patch("review_bot.review_runner.post_review", new_callable=AsyncMock)
@patch("review_bot.review_runner.get_state_store")
@patch("review_bot.review_runner.fetch_file_contents", new_callable=AsyncMock)
@patch("review_bot.review_runner.discover_agents_md", new_callable=AsyncMock)
@patch("review_bot.review_runner.assemble_prompt")
@patch("review_bot.review_runner.call_llm", new_callable=AsyncMock)
@patch("review_bot.review_runner.parse_review")
async def test_missing_per_repo_yml_proceeds_with_existing_config(
    mock_parse,
    mock_llm,
    mock_assemble,
    mock_discover,
    mock_fetch_file,
    mock_get_store,
    mock_post_review,
    mock_get_diff,
    mock_resolve,
):
    """When .github/review-bot.yml is absent (None), the review must still complete."""
    effective = MagicMock(model="gemini/flash", api_key="key", github_token="tok")
    mock_resolve.return_value = effective
    mock_fetch_file.return_value = None  # file not found

    diff_meta = _make_diff_metadata("src/foo.py")
    mock_get_diff.return_value = ("diff", diff_meta)

    store = AsyncMock()
    store.set_sha = AsyncMock()
    mock_get_store.return_value = store

    mock_discover.return_value = []
    mock_assemble.return_value = [{"role": "user", "content": "diff"}]
    mock_llm.return_value = '{"summary": "ok", "comments": []}'
    mock_parse.return_value = _make_review_result()

    # Must not raise
    await run_review(repo="owner/repo", pr_number=1, head_sha="sha", diff_type="full", before_sha=None)

    # resolve_effective_config is called twice: once for preliminary, once with None
    assert mock_resolve.call_count == 2
    # Second call must pass None as per_repo_yml_content
    second_call = mock_resolve.call_args_list[1]
    per_repo_arg = second_call.args[1] if len(second_call.args) > 1 else second_call.kwargs.get("per_repo_yml_content")
    assert per_repo_arg is None
