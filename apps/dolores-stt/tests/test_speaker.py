"""Tests for SpeakerIdentifier — embedding extraction and identification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dolores_stt.speaker import SpeakerIdentifier, _convert_to_wav


class TestSpeakerIdentifier:
    """Tests for speaker identification logic (mocked encoder)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.db_path = str(tmp_path / "test_speakers.db")
        self.identifier = SpeakerIdentifier(self.db_path, threshold=0.85)

        # Mock the VoiceEncoder to avoid loading the real model
        with patch("dolores_stt.speaker.SpeakerIdentifier.extract_embedding") as mock_extract:
            self.mock_extract = mock_extract
            # Open the store directly
            self.identifier.store.open()
            self.identifier._encoder = MagicMock()
            yield

        self.identifier.close()

    def _enroll_speaker(self, name: str, seed: int) -> str:
        """Helper to enroll a speaker with a deterministic embedding."""
        rng = np.random.RandomState(seed)
        emb = rng.randn(256).astype(np.float32)
        emb = emb / np.linalg.norm(emb)  # Normalize
        result = self.identifier.store.enroll(name, [emb])
        return result["id"]

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_identify_known_speaker(self, mock_convert, tmp_path):
        """Should identify an enrolled speaker with high confidence."""
        # Enroll Alice with a known embedding
        alice_emb = np.ones(256, dtype=np.float32)
        alice_emb = alice_emb / np.linalg.norm(alice_emb)
        self.identifier.store.enroll("Alice", [alice_emb])

        # Simulate identification with same embedding
        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path
        self.mock_extract.return_value = alice_emb

        result = self.identifier.identify(b"fake_audio", "audio/webm")
        assert result["speaker_name"] == "Alice"
        assert result["confidence"] >= 0.85

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_identify_unknown_speaker(self, mock_convert, tmp_path):
        """Should return None speaker for unknown voice."""
        # Enroll Alice
        alice_emb = np.zeros(256, dtype=np.float32)
        alice_emb[0] = 1.0  # Unit vector along axis 0
        self.identifier.store.enroll("Alice", [alice_emb])

        # Identify with an orthogonal embedding
        unknown_emb = np.zeros(256, dtype=np.float32)
        unknown_emb[1] = 1.0  # Unit vector along axis 1

        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path
        self.mock_extract.return_value = unknown_emb

        result = self.identifier.identify(b"fake_audio", "audio/webm")
        assert result["speaker_name"] is None
        assert result["speaker_id"] is None
        assert result["confidence"] < 0.85

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_identify_no_enrolled_speakers(self, mock_convert, tmp_path):
        """Should return empty result when no speakers are enrolled."""
        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path
        self.mock_extract.return_value = np.ones(256, dtype=np.float32)

        result = self.identifier.identify(b"fake_audio", "audio/webm")
        assert result["speaker_name"] is None
        assert result["confidence"] == 0.0

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_identify_best_match(self, mock_convert, tmp_path):
        """Should return the best matching speaker when multiple are enrolled."""
        # Enroll two speakers with distinct embeddings
        emb_alice = np.zeros(256, dtype=np.float32)
        emb_alice[0] = 1.0
        self.identifier.store.enroll("Alice", [emb_alice])

        emb_bob = np.zeros(256, dtype=np.float32)
        emb_bob[1] = 1.0
        self.identifier.store.enroll("Bob", [emb_bob])

        # Query with embedding closer to Alice
        query = np.zeros(256, dtype=np.float32)
        query[0] = 0.99
        query[1] = 0.01
        query = query / np.linalg.norm(query)

        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path
        self.mock_extract.return_value = query

        result = self.identifier.identify(b"fake_audio", "audio/webm")
        assert result["speaker_name"] == "Alice"

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_enroll_from_audio_samples(self, mock_convert, tmp_path):
        """Should enroll a speaker from audio samples."""
        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path

        emb = np.ones(256, dtype=np.float32)
        self.mock_extract.return_value = emb

        result = self.identifier.enroll(
            "Alice",
            [(b"audio1", "audio/webm"), (b"audio2", "audio/webm")],
        )
        assert result["name"] == "Alice"
        assert result["samples_count"] == 2

    @patch("dolores_stt.speaker._convert_to_wav")
    def test_enroll_validates_name(self, mock_convert, tmp_path):
        """Should reject invalid names during enrollment."""
        wav_path = tmp_path / "test.wav"
        wav_path.touch()
        mock_convert.return_value = wav_path
        self.mock_extract.return_value = np.ones(256, dtype=np.float32)

        with pytest.raises(ValueError, match="1-32 characters"):
            self.identifier.enroll(
                '"; DROP TABLE',
                [(b"audio", "audio/webm")],
            )


class TestConvertToWav:
    """Tests for audio preprocessing to WAV."""

    @patch("dolores_stt.speaker.subprocess.run")
    def test_calls_ffmpeg_with_correct_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        result = _convert_to_wav(b"fake_audio", "audio/webm")

        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-ar" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd

    @patch("dolores_stt.speaker.subprocess.run")
    def test_content_type_to_extension_mapping(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        # Test different content types
        for ct in ["audio/webm", "audio/ogg", "audio/mp4", "audio/wav"]:
            _convert_to_wav(b"fake", ct)

        assert mock_run.call_count == 4
