"""Tests for intent classification.

Tests the classification logic with mocked embeddings so no ONNX model is needed.
"""

import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from dolores_assistant import intent


@pytest.fixture(autouse=True)
def _reset_intent_state():
    """Reset global state between tests."""
    original_session = intent._session
    original_tokenizer = intent._tokenizer
    original_centroids = intent._intent_centroids
    yield
    intent._session = original_session
    intent._tokenizer = original_tokenizer
    intent._intent_centroids = original_centroids


class TestIntentExamples:
    """Validate the intent configuration."""

    def test_all_intents_have_tool_filters(self):
        for name, (tool_filter, examples) in intent.INTENT_EXAMPLES.items():
            assert isinstance(tool_filter, set), f"{name} tool_filter should be a set"
            assert len(tool_filter) > 0, f"{name} should have at least one filter"

    def test_all_intents_have_examples(self):
        for name, (_, examples) in intent.INTENT_EXAMPLES.items():
            assert len(examples) >= 5, f"{name} should have at least 5 examples, has {len(examples)}"

    def test_no_duplicate_examples(self):
        all_examples = []
        for _, (_, examples) in intent.INTENT_EXAMPLES.items():
            all_examples.extend(examples)
        assert len(all_examples) == len(set(all_examples)), "Duplicate examples found"

    def test_threshold_is_reasonable(self):
        assert 0.1 < intent.CONFIDENCE_THRESHOLD < 0.9


class TestClassifyIntent:
    """Test classify_intent with mocked embeddings."""

    def _setup_mock_centroids(self):
        """Set up mock centroids where each intent maps to a unit vector direction."""
        intent._session = MagicMock()  # Pretend model is loaded
        intent._tokenizer = MagicMock()
        intent._intent_centroids = {
            "todo": np.array([1.0, 0.0, 0.0]),
            "note": np.array([0.0, 1.0, 0.0]),
            "work": np.array([0.0, 0.0, 1.0]),
        }

    @patch.object(intent, "_encode")
    def test_high_confidence_todo(self, mock_encode):
        self._setup_mock_centroids()
        # Return embedding close to "todo" centroid
        mock_encode.return_value = np.array([[0.95, 0.1, 0.05]])
        name, tool_filter, score = intent.classify_intent("show my todos")
        assert name == "todo"
        assert tool_filter == {"todo"}
        assert score > intent.CONFIDENCE_THRESHOLD

    @patch.object(intent, "_encode")
    def test_high_confidence_note(self, mock_encode):
        self._setup_mock_centroids()
        mock_encode.return_value = np.array([[0.05, 0.95, 0.1]])
        name, tool_filter, score = intent.classify_intent("save a note")
        assert name == "note"
        assert tool_filter == {"note"}

    @patch.object(intent, "_encode")
    def test_high_confidence_work(self, mock_encode):
        self._setup_mock_centroids()
        mock_encode.return_value = np.array([[0.05, 0.1, 0.95]])
        name, tool_filter, score = intent.classify_intent("log my hours")
        assert name == "work"
        assert tool_filter == {"work"}

    @patch.object(intent, "_encode")
    def test_below_threshold_returns_none(self, mock_encode):
        self._setup_mock_centroids()
        # Embedding far from all centroids
        mock_encode.return_value = np.array([[0.3, 0.3, 0.3]])
        name, tool_filter, score = intent.classify_intent("what's the weather")
        assert name is None
        assert tool_filter is None
        assert score < intent.CONFIDENCE_THRESHOLD

    @patch.object(intent, "_encode")
    def test_returns_best_match(self, mock_encode):
        self._setup_mock_centroids()
        # Slightly closer to note than todo
        mock_encode.return_value = np.array([[0.4, 0.6, 0.1]])
        name, _, _ = intent.classify_intent("write something down")
        assert name == "note"


class TestMeanPool:
    def test_basic_pooling(self):
        # (batch=1, seq=3, hidden=2)
        embeddings = np.array([[[1.0, 2.0], [3.0, 4.0], [0.0, 0.0]]])
        mask = np.array([[1, 1, 0]])
        result = intent._mean_pool(embeddings, mask)
        # Should average only first 2 tokens: (1+3)/2=2, (2+4)/2=3
        np.testing.assert_allclose(result, [[2.0, 3.0]])

    def test_full_mask(self):
        embeddings = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        mask = np.array([[1, 1]])
        result = intent._mean_pool(embeddings, mask)
        np.testing.assert_allclose(result, [[2.0, 3.0]])

    def test_single_token(self):
        embeddings = np.array([[[5.0, 6.0], [0.0, 0.0]]])
        mask = np.array([[1, 0]])
        result = intent._mean_pool(embeddings, mask)
        np.testing.assert_allclose(result, [[5.0, 6.0]])


class TestNormalize:
    def test_unit_vectors(self):
        vectors = np.array([[3.0, 4.0]])
        result = intent._normalize(vectors)
        np.testing.assert_allclose(np.linalg.norm(result, axis=1), [1.0])
        np.testing.assert_allclose(result, [[0.6, 0.8]])

    def test_multiple_vectors(self):
        vectors = np.array([[1.0, 0.0], [0.0, 2.0]])
        result = intent._normalize(vectors)
        np.testing.assert_allclose(result, [[1.0, 0.0], [0.0, 1.0]])

    def test_already_normalized(self):
        vectors = np.array([[0.6, 0.8]])
        result = intent._normalize(vectors)
        np.testing.assert_allclose(result, [[0.6, 0.8]], atol=1e-6)
