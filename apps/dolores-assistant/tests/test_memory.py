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
