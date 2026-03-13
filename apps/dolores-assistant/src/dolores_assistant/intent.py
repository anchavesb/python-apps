"""Embedding-based intent classifier for tool routing.

Uses a small sentence-transformer model (all-MiniLM-L6-v2, ~80MB) to classify
user messages into tool domains. Runs on CPU with ~5ms inference per message.

Intent examples are defined declaratively — add new domains by adding entries
to INTENT_EXAMPLES.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from dolores_common.logging import get_logger

log = get_logger(__name__)

# Map: intent label → (tool_filter set, example phrases)
# The tool_filter set contains substrings matched against tool names.
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

# Confidence threshold: below this, the message is treated as general chat.
CONFIDENCE_THRESHOLD = 0.45

_model: SentenceTransformer | None = None
_intent_embeddings: dict[str, np.ndarray] | None = None


def _ensure_loaded() -> tuple[SentenceTransformer, dict[str, np.ndarray]]:
    """Lazy-load model and pre-compute intent embeddings on first use."""
    global _model, _intent_embeddings

    if _model is not None and _intent_embeddings is not None:
        return _model, _intent_embeddings

    log.info("loading_intent_model", model="all-MiniLM-L6-v2")
    _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    _intent_embeddings = {}
    for intent, (_, examples) in INTENT_EXAMPLES.items():
        embeddings = _model.encode(examples, normalize_embeddings=True)
        # Store mean embedding as the intent centroid
        _intent_embeddings[intent] = np.mean(embeddings, axis=0)
        # Normalize the centroid
        _intent_embeddings[intent] /= np.linalg.norm(_intent_embeddings[intent])

    log.info("intent_model_ready", intents=list(_intent_embeddings.keys()))
    return _model, _intent_embeddings


def classify_intent(message: str) -> tuple[str | None, set[str] | None, float]:
    """Classify a message into a tool intent.

    Returns:
        (intent_name, tool_filter, confidence)
        If confidence < threshold, returns (None, None, confidence).
    """
    model, intent_embs = _ensure_loaded()

    msg_embedding = model.encode([message], normalize_embeddings=True)[0]

    best_intent = None
    best_score = -1.0
    best_filter = None

    for intent, centroid in intent_embs.items():
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
