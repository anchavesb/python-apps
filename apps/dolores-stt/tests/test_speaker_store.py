"""Tests for SpeakerStore — SQLite persistence for speaker profiles."""

from __future__ import annotations

import numpy as np
import pytest

from dolores_stt.speaker_store import SpeakerStore


class TestSpeakerStore:
    """Tests for CRUD operations on SpeakerStore."""

    @pytest.fixture(autouse=True)
    def _setup_store(self, tmp_path):
        self.db_path = str(tmp_path / "test_speakers.db")
        self.store = SpeakerStore(self.db_path)
        self.store.open()
        yield
        self.store.close()

    def _fake_embedding(self, seed: int = 0) -> np.ndarray:
        rng = np.random.RandomState(seed)
        return rng.randn(256).astype(np.float32)

    def test_enroll_and_get(self):
        emb = self._fake_embedding(1)
        result = self.store.enroll("Alice", [emb], email="alice@example.com")

        assert result["name"] == "Alice"
        assert result["email"] == "alice@example.com"
        assert result["samples_count"] == 1

        profile = self.store.get(result["id"])
        assert profile is not None
        assert profile["name"] == "Alice"

    def test_enroll_multiple_samples_averages(self):
        emb1 = np.ones(256, dtype=np.float32)
        emb2 = np.ones(256, dtype=np.float32) * 3.0
        result = self.store.enroll("Bob", [emb1, emb2])
        assert result["samples_count"] == 2

        profiles = self.store.list_with_embeddings()
        assert len(profiles) == 1
        # Average of 1.0 and 3.0 should be 2.0
        np.testing.assert_allclose(profiles[0]["embedding"], np.full(256, 2.0), atol=1e-5)

    def test_list_speakers(self):
        self.store.enroll("Alice", [self._fake_embedding(1)])
        self.store.enroll("Bob", [self._fake_embedding(2)])

        speakers = self.store.list_speakers()
        assert len(speakers) == 2
        names = {s["name"] for s in speakers}
        assert names == {"Alice", "Bob"}
        # Should not include embedding blobs
        for s in speakers:
            assert "embedding" not in s

    def test_list_with_embeddings(self):
        self.store.enroll("Alice", [self._fake_embedding(1)])
        profiles = self.store.list_with_embeddings()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Alice"
        assert isinstance(profiles[0]["embedding"], np.ndarray)
        assert profiles[0]["embedding"].shape == (256,)
        assert profiles[0]["embedding_version"] == "resemblyzer-0.1.3"

    def test_delete(self):
        result = self.store.enroll("Alice", [self._fake_embedding(1)])
        assert self.store.delete(result["id"]) is True
        assert self.store.get(result["id"]) is None
        assert self.store.list_speakers() == []

    def test_delete_nonexistent(self):
        assert self.store.delete("nonexistent-id") is False

    def test_get_nonexistent(self):
        assert self.store.get("nonexistent-id") is None

    def test_update_embedding_running_average(self):
        emb1 = np.ones(256, dtype=np.float32) * 2.0
        result = self.store.enroll("Alice", [emb1])

        emb2 = np.ones(256, dtype=np.float32) * 4.0
        assert self.store.update_embedding(result["id"], emb2) is True

        profiles = self.store.list_with_embeddings()
        # Running average: (2.0 * 1 + 4.0) / 2 = 3.0
        np.testing.assert_allclose(profiles[0]["embedding"], np.full(256, 3.0), atol=1e-5)
        assert profiles[0]["samples_count"] == 2

    def test_update_embedding_nonexistent(self):
        assert self.store.update_embedding("nonexistent", self._fake_embedding()) is False


class TestNameValidation:
    """Tests for speaker name sanitization."""

    def test_valid_names(self):
        assert SpeakerStore.validate_name("Alice") == "Alice"
        assert SpeakerStore.validate_name("John Doe") == "John Doe"
        assert SpeakerStore.validate_name("user123") == "user123"
        assert SpeakerStore.validate_name("A") == "A"

    def test_strips_whitespace(self):
        assert SpeakerStore.validate_name("  Alice  ") == "Alice"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="1-32 characters"):
            SpeakerStore.validate_name("")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="1-32 characters"):
            SpeakerStore.validate_name("A" * 33)

    def test_rejects_special_characters(self):
        with pytest.raises(ValueError):
            SpeakerStore.validate_name('"; DROP TABLE speakers;--')

    def test_rejects_html_injection(self):
        with pytest.raises(ValueError):
            SpeakerStore.validate_name("<script>alert(1)</script>")

    def test_rejects_brackets(self):
        with pytest.raises(ValueError):
            SpeakerStore.validate_name("[Speaker: evil]")
