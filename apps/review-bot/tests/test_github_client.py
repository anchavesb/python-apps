"""Tests for review_bot.github_client.

HTTP calls are mocked by injecting an AsyncMock as the shared client via
``set_github_client``.  structlog's ``capture_logs`` context manager is used
to assert on structured log output (rate-limit warnings).
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from review_bot.github_client import (
    fetch_file_contents,
    get_diff,
    get_pr_info,
    list_open_prs,
    post_review,
    set_github_client,
)
from review_bot.schemas import InlineComment, ReviewResult
from structlog.testing import capture_logs

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int = 200,
    json_data=None,
    text: str = "",
    headers: dict | None = None,
) -> MagicMock:
    """Build a minimal httpx.Response mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def _rate_limit_headers(remaining: int, limit: int, reset_ts: str = "9999999999") -> dict:
    return {
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Reset": reset_ts,
    }


@pytest.fixture(autouse=True)
def _mock_client():
    """Install a fresh AsyncMock client before each test."""
    mock = AsyncMock(spec=httpx.AsyncClient)
    set_github_client(mock)
    return mock


# ---------------------------------------------------------------------------
# list_open_prs
# ---------------------------------------------------------------------------


class TestListOpenPrs:
    async def test_returns_pr_info_list(self, _mock_client):
        _mock_client.get.return_value = _make_response(
            json_data=[
                {"number": 1, "title": "Fix bug", "head": {"sha": "abc123"}},
                {"number": 2, "title": "Add feature", "head": {"sha": "def456"}},
            ]
        )

        result = await list_open_prs("owner", "repo", "token")

        assert len(result) == 2
        assert result[0].number == 1
        assert result[0].head_sha == "abc123"
        assert result[0].title == "Fix bug"
        assert result[1].number == 2
        assert result[1].head_sha == "def456"

    async def test_empty_repo_returns_empty_list(self, _mock_client):
        _mock_client.get.return_value = _make_response(json_data=[])
        result = await list_open_prs("owner", "repo", "token")
        assert result == []


# ---------------------------------------------------------------------------
# get_pr_info
# ---------------------------------------------------------------------------


class TestGetPrInfo:
    async def test_returns_single_pr_info(self, _mock_client):
        _mock_client.get.return_value = _make_response(
            json_data={"number": 42, "title": "My PR", "head": {"sha": "sha999"}}
        )

        pr = await get_pr_info("owner", "repo", 42, "token")

        assert pr.number == 42
        assert pr.head_sha == "sha999"
        assert pr.title == "My PR"

    async def test_calls_correct_url(self, _mock_client):
        _mock_client.get.return_value = _make_response(json_data={"number": 7, "title": "T", "head": {"sha": "s"}})

        await get_pr_info("myorg", "myrepo", 7, "tok")

        url, *_ = _mock_client.get.call_args.args
        assert "myorg/myrepo/pulls/7" in url

    async def test_404_raises_http_404_not_502(self, _mock_client):
        """GitHub 404 for a PR must surface as HTTP 404, not a generic 502."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 404
        resp.headers = {}
        resp.raise_for_status.return_value = None  # never reached
        _mock_client.get.return_value = resp

        from fastapi import HTTPException as FastAPIHTTPException

        with pytest.raises(FastAPIHTTPException) as exc_info:
            await get_pr_info("owner", "repo", 99, "tok")

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_diff — full mode
# ---------------------------------------------------------------------------

_PATCH = "@@ -1,3 +1,5 @@\n line1\n+added_line\n line2\n+another_added\n line3"


class TestGetDiffFull:
    async def test_full_mode_returns_diff_text_and_metadata(self, _mock_client):
        _mock_client.get.return_value = _make_response(json_data=[{"filename": "src/main.py", "patch": _PATCH}])

        diff_text, meta = await get_diff("o", "r", 1, "full", None, None, "tok")

        assert "src/main.py" in diff_text
        assert "src/main.py" in meta.files
        # Lines 2 and 4 are added lines in the patch (new-file numbering)
        assert 2 in meta.files["src/main.py"].changed_lines
        assert 4 in meta.files["src/main.py"].changed_lines

    async def test_full_mode_paginates(self, _mock_client):
        """A first page of 100 files must trigger a second request."""
        page1 = [{"filename": f"f{i}.py", "patch": "@@ -1 +1 @@\n+x"} for i in range(100)]
        page2 = [{"filename": "last.py", "patch": "@@ -1 +1 @@\n+y"}]
        _mock_client.get.side_effect = [
            _make_response(json_data=page1),
            _make_response(json_data=page2),
        ]

        _, meta = await get_diff("o", "r", 1, "full", None, None, "tok")

        assert len(meta.files) == 101
        assert "last.py" in meta.files

    async def test_file_without_patch_has_no_changed_lines(self, _mock_client):
        """Binary/deleted files often have no patch field."""
        _mock_client.get.return_value = _make_response(json_data=[{"filename": "image.png"}])

        _, meta = await get_diff("o", "r", 1, "full", None, None, "tok")

        assert meta.files["image.png"].changed_lines == []


# ---------------------------------------------------------------------------
# get_diff — incremental mode
# ---------------------------------------------------------------------------

_INCREMENTAL_DIFF = (
    "diff --git a/src/utils.py b/src/utils.py\n"
    "index 111..222 100644\n"
    "--- a/src/utils.py\n"
    "+++ b/src/utils.py\n"
    "@@ -10,3 +10,4 @@\n"
    " existing\n"
    "+new_line\n"
    " other\n"
)


class TestGetDiffIncremental:
    async def test_incremental_returns_raw_diff_and_metadata(self, _mock_client):
        _mock_client.get.return_value = _make_response(text=_INCREMENTAL_DIFF)

        diff_text, meta = await get_diff("o", "r", 1, "incremental", "sha_before", "sha_after", "tok")

        assert diff_text == _INCREMENTAL_DIFF
        assert "src/utils.py" in meta.files
        assert 11 in meta.files["src/utils.py"].changed_lines

    async def test_incremental_uses_compare_url(self, _mock_client):
        _mock_client.get.return_value = _make_response(text=_INCREMENTAL_DIFF)

        await get_diff("org", "rep", 5, "incremental", "before_sha", "after_sha", "tok")

        url, *_ = _mock_client.get.call_args.args
        assert "compare/before_sha...after_sha" in url

    async def test_incremental_uses_diff_accept_header(self, _mock_client):
        _mock_client.get.return_value = _make_response(text=_INCREMENTAL_DIFF)

        await get_diff("o", "r", 1, "incremental", "b", "a", "tok")

        headers = _mock_client.get.call_args.kwargs.get("headers", {})
        assert headers.get("Accept") == "application/vnd.github.diff"


# ---------------------------------------------------------------------------
# fetch_file_contents
# ---------------------------------------------------------------------------


class TestFetchFileContents:
    async def test_returns_decoded_content_when_found(self, _mock_client):
        encoded = base64.b64encode(b"hello world").decode()
        _mock_client.get.return_value = _make_response(json_data={"content": encoded})

        result = await fetch_file_contents("o", "r", "AGENTS.md", "main", "tok")

        assert result == "hello world"

    async def test_returns_none_on_404(self, _mock_client):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 404
        resp.headers = {}
        resp.raise_for_status.return_value = None  # 404 handled before raise_for_status
        _mock_client.get.return_value = resp

        result = await fetch_file_contents("o", "r", "AGENTS.md", "main", "tok")

        assert result is None

    async def test_content_with_embedded_newlines_decoded_correctly(self, _mock_client):
        """GitHub wraps base64 content at 60 chars with newlines."""
        raw = b"line one\nline two\n"
        encoded_with_newlines = base64.b64encode(raw).decode()
        # Simulate GitHub's chunked encoding
        chunked = "\n".join(encoded_with_newlines[i : i + 60] for i in range(0, len(encoded_with_newlines), 60))
        _mock_client.get.return_value = _make_response(json_data={"content": chunked})

        result = await fetch_file_contents("o", "r", "README.md", "abc", "tok")

        assert result == "line one\nline two\n"


# ---------------------------------------------------------------------------
# post_review
# ---------------------------------------------------------------------------


class TestPostReview:
    async def test_posts_review_with_body_and_comments(self, _mock_client):
        _mock_client.post.return_value = _make_response(json_data={"id": 1})
        result = ReviewResult(
            summary="Overall summary",
            inline_comments=[
                InlineComment(path="src/main.py", line=5, body="Consider renaming this"),
            ],
        )

        await post_review("owner", "repo", 10, result, "tok")

        _mock_client.post.assert_called_once()
        _, kwargs = _mock_client.post.call_args
        payload = kwargs.get("json") or _mock_client.post.call_args.kwargs["json"]
        assert payload["body"] == "Overall summary"
        assert payload["event"] == "COMMENT"
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["path"] == "src/main.py"
        assert payload["comments"][0]["line"] == 5
        assert payload["comments"][0]["side"] == "RIGHT"

    async def test_posts_to_correct_reviews_url(self, _mock_client):
        _mock_client.post.return_value = _make_response(json_data={"id": 2})
        result = ReviewResult(summary="s", inline_comments=[])

        await post_review("myorg", "myrepo", 99, result, "tok")

        url = _mock_client.post.call_args.args[0]
        assert "myorg/myrepo/pulls/99/reviews" in url


# ---------------------------------------------------------------------------
# Rate limit warnings
# ---------------------------------------------------------------------------


class TestRateLimitWarning:
    async def test_warning_logged_at_2_percent_remaining(self, _mock_client):
        _mock_client.get.return_value = _make_response(
            json_data=[],
            headers=_rate_limit_headers(remaining=100, limit=5000),
        )

        with capture_logs() as cap_logs:
            await list_open_prs("o", "r", "tok")

        warning_events = [e for e in cap_logs if e.get("event") == "github_rate_limit_low"]
        assert len(warning_events) == 1
        assert warning_events[0]["remaining"] == 100
        assert warning_events[0]["limit"] == 5000

    async def test_no_warning_at_30_percent_remaining(self, _mock_client):
        _mock_client.get.return_value = _make_response(
            json_data=[],
            headers=_rate_limit_headers(remaining=1500, limit=5000),
        )

        with capture_logs() as cap_logs:
            await list_open_prs("o", "r", "tok")

        warning_events = [e for e in cap_logs if e.get("event") == "github_rate_limit_low"]
        assert len(warning_events) == 0

    async def test_no_warning_when_headers_absent(self, _mock_client):
        _mock_client.get.return_value = _make_response(json_data=[])

        with capture_logs() as cap_logs:
            await list_open_prs("o", "r", "tok")

        warning_events = [e for e in cap_logs if e.get("event") == "github_rate_limit_low"]
        assert len(warning_events) == 0
