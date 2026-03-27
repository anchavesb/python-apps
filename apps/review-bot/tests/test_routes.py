"""Tests for routes.py — POST /v1/review response codes and PSK authentication."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import review_bot.review_runner as rr
from fastapi import FastAPI
from httpx import ASGITransport
from review_bot.config import RegistryError
from review_bot.github_client import set_github_client
from review_bot.routes import router
from review_bot.schemas import PRInfo
from review_bot.state_store import set_state_store

pytestmark = pytest.mark.anyio

_PSK = "test-psk-secret"
_AUTH_HEADER = f"Bearer {_PSK}"


# ---------------------------------------------------------------------------
# App fixture — minimal FastAPI app wired with the review router
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def mock_github():
    client = AsyncMock()
    set_github_client(client)
    return client


@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.get_sha = AsyncMock(return_value=None)
    store.set_sha = AsyncMock()
    set_state_store(store)
    return store


@pytest.fixture(autouse=True)
def _init_semaphore():
    """Provide a fresh semaphore for each test."""
    original = rr._semaphore
    rr.init_semaphore(3)
    yield
    rr._semaphore = original


@pytest.fixture
def _psk_env(monkeypatch):
    monkeypatch.setenv("REVIEW_BOT_PSK", _PSK)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# PSK authentication
# ---------------------------------------------------------------------------


class TestPSKAuth:
    async def test_missing_auth_header_returns_401(self, client, mock_github, mock_store, _psk_env):
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=1, head_sha="abc", title="T", owner="o", repo="r")
        )
        with patch("review_bot.routes.resolve_effective_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post("/v1/review", json={"repo": "o/r", "pr_number": 1})
        assert resp.status_code == 401

    async def test_wrong_psk_returns_401(self, client, mock_github, mock_store, _psk_env):
        with patch("review_bot.routes.resolve_effective_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post(
                "/v1/review",
                json={"repo": "o/r", "pr_number": 1},
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401

    async def test_missing_psk_env_skips_auth(self, client, mock_github, mock_store, monkeypatch):
        monkeypatch.delenv("REVIEW_BOT_PSK", raising=False)
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=1, head_sha="abc", title="T", owner="o", repo="r")
        )
        with (
            patch("review_bot.routes.resolve_effective_config") as mock_cfg,
            patch("review_bot.routes.run_review", new_callable=AsyncMock),
        ):
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post("/v1/review", json={"repo": "o/r", "pr_number": 1})
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# POST /v1/review — response codes
# ---------------------------------------------------------------------------


class TestTriggerReview:
    async def test_valid_psk_new_pr_returns_202_accepted(self, client, mock_github, mock_store, _psk_env):
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=5, head_sha="newsha", title="PR", owner="owner", repo="repo")
        )
        mock_store.get_sha = AsyncMock(return_value=None)

        with (
            patch("review_bot.routes.resolve_effective_config") as mock_cfg,
            patch("review_bot.routes.run_review", new_callable=AsyncMock),
        ):
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post(
                "/v1/review",
                json={"repo": "owner/repo", "pr_number": 5},
                headers={"Authorization": _AUTH_HEADER},
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["repo"] == "owner/repo"
        assert body["pr_number"] == 5

    async def test_already_reviewed_force_false_returns_200_skipped(self, client, mock_github, mock_store, _psk_env):
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=3, head_sha="same-sha", title="PR", owner="owner", repo="repo")
        )
        mock_store.get_sha = AsyncMock(return_value="same-sha")

        with patch("review_bot.routes.resolve_effective_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post(
                "/v1/review",
                json={"repo": "owner/repo", "pr_number": 3, "force": False},
                headers={"Authorization": _AUTH_HEADER},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "already_reviewed"
        assert body["sha"] == "same-sha"

    async def test_already_reviewed_force_true_returns_202(self, client, mock_github, mock_store, _psk_env):
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=3, head_sha="same-sha", title="PR", owner="owner", repo="repo")
        )
        mock_store.get_sha = AsyncMock(return_value="same-sha")

        with (
            patch("review_bot.routes.resolve_effective_config") as mock_cfg,
            patch("review_bot.routes.run_review", new_callable=AsyncMock),
        ):
            mock_cfg.return_value = MagicMock(github_token="tok")
            resp = await client.post(
                "/v1/review",
                json={"repo": "owner/repo", "pr_number": 3, "force": True},
                headers={"Authorization": _AUTH_HEADER},
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"

    async def test_unregistered_repo_returns_400(self, client, mock_github, mock_store, _psk_env):
        with patch("review_bot.routes.resolve_effective_config") as mock_cfg:
            mock_cfg.side_effect = RegistryError("Repository 'o/r' is not registered in repos.yml")
            resp = await client.post(
                "/v1/review",
                json={"repo": "o/r", "pr_number": 1},
                headers={"Authorization": _AUTH_HEADER},
            )

        assert resp.status_code == 400
        assert "not registered" in resp.json()["detail"]

    async def test_semaphore_exhausted_returns_503_with_retry_after(self, client, mock_github, mock_store, _psk_env):
        mock_github.get_pr_info = AsyncMock(
            return_value=PRInfo(number=1, head_sha="sha", title="PR", owner="owner", repo="repo")
        )
        mock_store.get_sha = AsyncMock(return_value=None)

        # Exhaust the semaphore
        sem = rr.get_semaphore()
        acquired = []
        while not sem.locked():
            await sem.acquire()
            acquired.append(True)

        try:
            with patch("review_bot.routes.resolve_effective_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(github_token="tok")
                resp = await client.post(
                    "/v1/review",
                    json={"repo": "owner/repo", "pr_number": 1},
                    headers={"Authorization": _AUTH_HEADER},
                )
        finally:
            for _ in acquired:
                sem.release()

        assert resp.status_code == 503
        assert resp.headers.get("retry-after") == "30"
