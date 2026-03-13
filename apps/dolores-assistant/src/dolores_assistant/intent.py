"""Embedding-based intent classifier for tool routing.

Uses all-MiniLM-L6-v2 via ONNX Runtime + tokenizers (no PyTorch).
Image size: ~150MB total vs ~2GB+ with sentence-transformers/PyTorch.

Intent examples are defined declaratively — add new domains by adding entries
to INTENT_EXAMPLES.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from dolores_common.logging import get_logger

log = get_logger(__name__)

# Map: intent label → (tool_filter set, example phrases)
INTENT_EXAMPLES: dict[str, tuple[set[str], list[str]]] = {
    "todo": ({"todo"}, [
        "show my todos",
        "what's on my todo list",
        "add a task",
        "create a todo",
        "I need to buy milk",
        "remind me to call the doctor",
        "mark that task as done",
        "delete the first todo",
        "what tasks do I have",
        "check my task list",
        "add a reminder",
        "complete the grocery task",
        "remove that todo",
        "any pending tasks",
        "what do I need to do today",
        "add pick up dry cleaning to my list",
    ]),
    "note": ({"note"}, [
        "save a note",
        "write a note about the meeting",
        "show my notes",
        "create a note",
        "take a memo",
        "jot this down",
        "delete that note",
        "what notes do I have",
        "find my notes about the project",
        "add a note saying the server IP is 10.0.0.1",
        "update my meeting notes",
        "list all notes",
    ]),
    "work": ({"work"}, [
        "log my work",
        "add a work item",
        "show work log",
        "track my hours",
        "what work did I do today",
        "log 2 hours on the API project",
        "show my work items",
        "delete that work entry",
        "update my work log",
    ]),
}

CONFIDENCE_THRESHOLD = 0.45

_session: ort.InferenceSession | None = None
_tokenizer: Tokenizer | None = None
_intent_centroids: dict[str, np.ndarray] | None = None


def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Mean pooling: average token embeddings, respecting attention mask."""
    mask_expanded = np.expand_dims(attention_mask, axis=-1).astype(np.float32)
    summed = np.sum(token_embeddings * mask_expanded, axis=1)
    counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize each row."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, a_min=1e-9, a_max=None)


def _encode(texts: list[str]) -> np.ndarray:
    """Tokenize and run ONNX inference, returning normalized embeddings."""
    assert _session is not None and _tokenizer is not None

    # Tokenize
    encodings = _tokenizer.encode_batch(texts)
    max_len = max(len(e.ids) for e in encodings)

    input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
    attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
    token_type_ids = np.zeros((len(texts), max_len), dtype=np.int64)

    for i, enc in enumerate(encodings):
        length = len(enc.ids)
        input_ids[i, :length] = enc.ids
        attention_mask[i, :length] = enc.attention_mask

    # Run ONNX model
    outputs = _session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )

    # outputs[0] is token_embeddings: (batch, seq_len, hidden_size)
    pooled = _mean_pool(outputs[0], attention_mask)
    return _normalize(pooled)


def _get_model_dir() -> Path:
    """Find the pre-downloaded ONNX model directory."""
    # Check common locations
    for base in [
        Path.home() / ".cache" / "dolores-intent",
        Path("/app/models/intent"),
    ]:
        if (base / "model.onnx").exists():
            return base
    raise FileNotFoundError(
        "Intent model not found. Run: python -m dolores_assistant.intent_download"
    )


def _ensure_loaded() -> None:
    """Lazy-load ONNX model and pre-compute intent centroids."""
    global _session, _tokenizer, _intent_centroids

    if _session is not None:
        return

    model_dir = _get_model_dir()
    log.info("loading_intent_model", path=str(model_dir))

    _tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    _session = ort.InferenceSession(
        str(model_dir / "model.onnx"),
        providers=["CPUExecutionProvider"],
    )

    # Pre-compute intent centroids
    _intent_centroids = {}
    for intent, (_, examples) in INTENT_EXAMPLES.items():
        embeddings = _encode(examples)
        centroid = np.mean(embeddings, axis=0)
        centroid /= np.linalg.norm(centroid)
        _intent_centroids[intent] = centroid

    log.info("intent_model_ready", intents=list(_intent_centroids.keys()))


def classify_intent(message: str) -> tuple[str | None, set[str] | None, float]:
    """Classify a message into a tool intent.

    Returns:
        (intent_name, tool_filter, confidence)
        If confidence < threshold, returns (None, None, confidence).
    """
    _ensure_loaded()
    assert _intent_centroids is not None

    msg_embedding = _encode([message])[0]

    best_intent = None
    best_score = -1.0
    best_filter = None

    for intent, centroid in _intent_centroids.items():
        score = float(np.dot(msg_embedding, centroid))
        if score > best_score:
            best_score = score
            best_intent = intent
            best_filter = INTENT_EXAMPLES[intent][0]

    if best_score < CONFIDENCE_THRESHOLD:
        log.debug("intent_below_threshold", message=message[:80], best=best_intent, score=best_score)
        return None, None, best_score

    log.info("intent_classified", message=message[:80], intent=best_intent, score=round(best_score, 3))
    return best_intent, best_filter, best_score
