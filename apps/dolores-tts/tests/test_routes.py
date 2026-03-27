"""Tests for TTS API routes.

Uses FastAPI's TestClient (sync) with mocked engine and voice store.
Heavy ML engines and real DB are never instantiated.
"""

from __future__ import annotations

import io
import struct
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dolores_tts import routes
from dolores_tts.routes import router, set_engine, set_voice_store


@pytest.fixture()
def mock_engine():
    engine = MagicMock()
    engine.is_loaded = True
    engine.name = "coqui_xtts"
    # Minimal valid WAV: 44-byte header + 2 bytes of PCM
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 38))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<I", 24000))
    buf.write(struct.pack("<I", 48000))
    buf.write(struct.pack("<H", 2))
    buf.write(struct.pack("<H", 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", 2))
    buf.write(b"\x00\x00")
    engine.synthesize.return_value = buf.getvalue()
    return engine


@pytest.fixture()
def mock_store():
    store = MagicMock()
    store.list_profiles = AsyncMock(return_value=[])
    store.get_profile = AsyncMock(return_value=None)
    store.create = AsyncMock(return_value={
        "id": "abc12345",
        "name": "TestVoice",
        "engine": "coqui_xtts",
        "ref_text": None,
    })
    store.delete = AsyncMock(return_value=True)
    return store


@pytest.fixture()
def app(mock_engine, mock_store):
    set_engine(mock_engine)
    set_voice_store(mock_store)
    _app = FastAPI()
    _app.include_router(router)
    yield _app
    # Reset module-level singletons
    routes._engine = None
    routes._voice_store = None


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /v1/synthesize
# ---------------------------------------------------------------------------

class TestSynthesize:
    def test_returns_wav_audio(self, client, mock_engine):
        resp = client.post("/v1/synthesize", json={"text": "Hello world"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.content[:4] == b"RIFF"

    def test_calls_engine_synthesize(self, client, mock_engine):
        client.post("/v1/synthesize", json={"text": "Test text", "voice_id": "myvoice"})
        mock_engine.synthesize.assert_called_once()
        call_kwargs = mock_engine.synthesize.call_args.kwargs
        assert call_kwargs["text"] == "Test text"
        assert call_kwargs["voice_id"] == "myvoice"

    def test_empty_text_returns_400(self, client):
        resp = client.post("/v1/synthesize", json={"text": "   "})
        assert resp.status_code == 400

    def test_text_too_long_returns_422(self, client):
        resp = client.post("/v1/synthesize", json={"text": "x" * 5001})
        assert resp.status_code == 422  # Pydantic max_length

    def test_engine_not_loaded_returns_503(self, client, mock_engine):
        mock_engine.is_loaded = False
        resp = client.post("/v1/synthesize", json={"text": "Hello"})
        assert resp.status_code == 503

    def test_synthesize_passes_ref_text_from_store(self, client, mock_engine, mock_store):
        mock_store.get_profile = AsyncMock(return_value={
            "id": "abc12345", "name": "Voice", "engine": "f5_tts",
            "ref_text": "sample reference text", "description": "", "created_at": "2026-01-01T00:00:00Z",
        })
        client.post("/v1/synthesize", json={"text": "Hello", "voice_id": "abc12345"})
        call_kwargs = mock_engine.synthesize.call_args.kwargs
        assert call_kwargs["ref_text"] == "sample reference text"

    def test_synthesize_continues_when_store_unavailable(self, client, mock_engine):
        """Store errors must not fail synthesis — graceful degradation."""
        routes._voice_store = None  # simulate store not initialized
        resp = client.post("/v1/synthesize", json={"text": "Hello"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/voices
# ---------------------------------------------------------------------------

class TestListVoices:
    def test_returns_empty_list(self, client, mock_store):
        mock_store.list_profiles = AsyncMock(return_value=[])
        resp = client.get("/v1/voices")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_profiles(self, client, mock_store):
        mock_store.list_profiles = AsyncMock(return_value=[{
            "id": "abc12345", "name": "Voice1", "description": "",
            "engine": "coqui_xtts", "ref_text": None, "created_at": "2026-01-01T00:00:00Z",
        }])
        resp = client.get("/v1/voices")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Voice1"

    def test_store_not_initialized_returns_503(self, client):
        routes._voice_store = None
        resp = client.get("/v1/voices")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/voices/{voice_id}
# ---------------------------------------------------------------------------

class TestGetVoice:
    def test_returns_profile(self, client, mock_store):
        mock_store.get_profile = AsyncMock(return_value={
            "id": "abc12345", "name": "Voice1", "description": "",
            "engine": "coqui_xtts", "ref_text": None, "created_at": "2026-01-01T00:00:00Z",
        })
        resp = client.get("/v1/voices/abc12345")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Voice1"

    def test_not_found_returns_404(self, client, mock_store):
        mock_store.get_profile = AsyncMock(return_value=None)
        resp = client.get("/v1/voices/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/voices
# ---------------------------------------------------------------------------

class TestCreateVoice:
    def _audio_file(self, content: bytes = b"fake_wav", content_type: str = "audio/wav"):
        return ("file", ("reference.wav", BytesIO(content), content_type))

    @patch("dolores_tts.routes._convert_to_wav", new_callable=AsyncMock)
    def test_creates_voice_profile(self, mock_convert, client, mock_store):
        mock_convert.return_value = b"converted_wav"
        resp = client.post(
            "/v1/voices?name=MyVoice&ref_text=Hello+world",
            files=[self._audio_file()],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "abc12345"
        assert data["name"] == "TestVoice"

    def test_missing_ref_text_returns_422(self, client):
        resp = client.post(
            "/v1/voices?name=MyVoice",
            files=[self._audio_file()],
        )
        assert resp.status_code == 422

    @patch("dolores_tts.routes._convert_to_wav", new_callable=AsyncMock)
    def test_creates_with_ref_text(self, mock_convert, client, mock_store):
        mock_convert.return_value = b"converted_wav"
        client.post(
            "/v1/voices?name=F5Voice&ref_text=Hello+world",
            files=[self._audio_file()],
        )
        call_kwargs = mock_store.create.call_args.kwargs
        assert call_kwargs["ref_text"] == "Hello world"

    def test_non_audio_content_type_returns_415(self, client):
        resp = client.post(
            "/v1/voices?name=BadVoice&ref_text=Hello",
            files=[self._audio_file(content_type="text/plain")],
        )
        assert resp.status_code == 415

    def test_empty_file_returns_400(self, client):
        resp = client.post(
            "/v1/voices?name=EmptyVoice&ref_text=Hello",
            files=[self._audio_file(content=b"")],
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /v1/voices/{voice_id}
# ---------------------------------------------------------------------------

class TestDeleteVoice:
    def test_delete_existing_returns_204(self, client, mock_store):
        mock_store.delete = AsyncMock(return_value=True)
        resp = client.delete("/v1/voices/abc12345")
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(self, client, mock_store):
        mock_store.delete = AsyncMock(return_value=False)
        resp = client.delete("/v1/voices/ghost")
        assert resp.status_code == 404

    def test_delete_calls_store_with_correct_id(self, client, mock_store):
        mock_store.delete = AsyncMock(return_value=True)
        client.delete("/v1/voices/target-id")
        mock_store.delete.assert_called_once_with("target-id")
