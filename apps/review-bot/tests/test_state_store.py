"""Tests for state_store.py — aiosqlite-backed PR state store."""

from __future__ import annotations

import pytest

from review_bot.state_store import StateStore, get_state_store, set_state_store

pytestmark = pytest.mark.anyio


@pytest.fixture
async def store(tmp_path):
    s = StateStore(str(tmp_path / "test_state.db"))
    await s.init()
    yield s
    await s.close()


async def test_get_sha_returns_none_for_unknown_key(store):
    result = await store.get_sha("owner/repo", 42)
    assert result is None


async def test_set_sha_then_get_sha_returns_stored_value(store):
    await store.set_sha("owner/repo", 1, "abc123")
    result = await store.get_sha("owner/repo", 1)
    assert result == "abc123"


async def test_set_sha_twice_upserts_without_error(store):
    await store.set_sha("owner/repo", 7, "sha_first")
    await store.set_sha("owner/repo", 7, "sha_second")
    result = await store.get_sha("owner/repo", 7)
    assert result == "sha_second"


async def test_init_called_twice_is_idempotent(tmp_path):
    s = StateStore(str(tmp_path / "idempotent.db"))
    await s.init()
    await s.init()
    await s.set_sha("owner/repo", 99, "deadbeef")
    result = await s.get_sha("owner/repo", 99)
    assert result == "deadbeef"
    await s.close()


async def test_different_repos_are_independent(store):
    await store.set_sha("owner/repo-a", 1, "sha_a")
    await store.set_sha("owner/repo-b", 1, "sha_b")
    assert await store.get_sha("owner/repo-a", 1) == "sha_a"
    assert await store.get_sha("owner/repo-b", 1) == "sha_b"


def test_get_state_store_raises_when_uninitialized():
    import review_bot.state_store as ss

    original = ss._store
    ss._store = None
    try:
        with pytest.raises(RuntimeError, match="StateStore not initialized"):
            get_state_store()
    finally:
        ss._store = original


def test_set_and_get_state_store_singleton(tmp_path):
    import review_bot.state_store as ss

    original = ss._store
    s = StateStore(str(tmp_path / "singleton.db"))
    try:
        set_state_store(s)
        assert get_state_store() is s
    finally:
        ss._store = original
