import os
from unittest.mock import patch

import pytest

from dolores_assistant.memory import MemoryStore


@pytest.mark.anyio
async def test_memory_store_add_and_search():
    db_path = "data/test_memory.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = MemoryStore(db_path=db_path)

    # Mock get_embedding to return consistent vectors
    with patch("dolores_assistant.memory.get_embedding") as mock_emb:
        # "I like coffee"
        mock_emb.return_value = [1.0] + [0.0] * 383
        await store.add_memory("I like coffee")

        # "My car is red"
        mock_emb.return_value = [0.0, 1.0] + [0.0] * 382
        await store.add_memory("My car is red")

        # Search for coffee related things
        mock_emb.return_value = [0.9, 0.1] + [0.0] * 382
        results = await store.search_memories("coffee", limit=1)

        assert len(results) == 1
        assert "coffee" in results[0]["text"]
        assert results[0]["score"] > 0.8

        # Search for car related things
        mock_emb.return_value = [0.1, 0.9] + [0.0] * 382
        results = await store.search_memories("vehicle", limit=1)

        assert len(results) == 1
        assert "car" in results[0]["text"]
        assert results[0]["score"] > 0.8

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.anyio
async def test_memory_multiuser_isolation():
    db_path = "data/test_memory_isolation.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    store = MemoryStore(db_path=db_path)

    with patch("dolores_assistant.memory.get_embedding") as mock_emb:
        # Save a fact for user1
        mock_emb.return_value = [1.0] + [0.0] * 383
        await store.add_memory("Andrea likes Python", user_id="user1")

        # Save a fact for user2
        mock_emb.return_value = [1.0] + [0.0] * 383
        await store.add_memory("Bob likes Java", user_id="user2")

        # Query as user1 for Python related things
        mock_emb.return_value = [1.0] + [0.0] * 383
        results1 = await store.search_memories("programming language", user_id="user1", limit=5)

        assert len(results1) == 1
        assert "Andrea" in results1[0]["text"]
        assert "Bob" not in results1[0]["text"]

        # Query as user2 for the same embedding
        results2 = await store.search_memories("programming language", user_id="user2", limit=5)

        assert len(results2) == 1
        assert "Bob" in results2[0]["text"]
        assert "Andrea" not in results2[0]["text"]

    if os.path.exists(db_path):
        os.remove(db_path)
