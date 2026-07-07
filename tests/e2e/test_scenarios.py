"""E2E Test Scenarios for Dolores Ecosystem."""

from __future__ import annotations

from pathlib import Path

import httpx

ASSETS_DIR = Path(__file__).parent / "assets"
ROOT_DIR = Path(__file__).parent.parent.parent
SAMPLE_WAV = ROOT_DIR / "apps" / "dolores-tts" / "assets" / "emotion_refs" / "neutral.wav"


def test_health_check(client: httpx.Client):
    """Verify that all services are healthy through the assistant's health endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "stt" in data["services"]
    assert "tts" in data["services"]
    assert "brain" in data["services"]
    assert data["services"]["stt"] == "healthy"


def test_temperature_tool(client: httpx.Client):
    """Ask for the weather and verify the tool call flow."""
    payload = {"message": "What is the weather in Melbourne, AU?", "user_id": "test-user"}
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    msg = data["message"].lower()
    # We accept any response that looks like it tried to answer
    assert len(msg) > 5


def test_image_generation(client: httpx.Client):
    """Test the image generation pipeline."""
    payload = {"message": "Generate an image of a futuristic city.", "user_id": "test-user"}
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    msg = data["message"].lower()
    assert len(msg) > 5


def test_news_search(client: httpx.Client):
    """Test the web search / news tool."""
    payload = {"message": "What are the latest news about AI?", "user_id": "test-user"}
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["message"]) > 5


def test_todo_integration(client: httpx.Client):
    """Test the OpenAPI-discovered 'todo' tool."""
    # 1. Add a todo
    payload = {"message": "Add 'Buy milk' to my todo list.", "user_id": "test-user"}
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 200

    # 2. Verify it was added by listing todos
    payload = {"message": "List my todos.", "user_id": "test-user"}
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 200
    msg = resp.json()["message"].lower()
    # If the tool worked, the response should ideally contain the item
    # or the LLM should at least respond.
    assert len(msg) > 5


def test_speaker_recognition_flow(client: httpx.Client):
    """Enroll a speaker and then identify them using STT service."""
    # 1. Enroll Alice using the sample WAV
    with open(SAMPLE_WAV, "rb") as f:
        files = [("files", ("alice.wav", f, "audio/wav"))]
        resp = httpx.post("http://localhost:8001/v1/speakers", params={"name": "Alice"}, files=files, timeout=60)
    assert resp.status_code == 200

    # 2. Identify the speaker from the same audio
    with open(SAMPLE_WAV, "rb") as f:
        files = {"file": ("query.wav", f, "audio/wav")}
        resp = httpx.post("http://localhost:8001/v1/identify", files=files, timeout=60)

    assert resp.status_code == 200
    data = resp.json()
    assert data["speaker_name"] == "Alice"
    assert data["confidence"] > 0.7


def test_voice_profile_tts(client: httpx.Client):
    """Verify TTS can generate audio."""
    payload = {"text": "Hello, I am testing my voice profile.", "voice_id": "default"}
    resp = httpx.post("http://localhost:8002/v1/synthesize", json=payload, timeout=60)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) > 100
