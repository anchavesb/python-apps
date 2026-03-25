"""Tests for TTS engine implementations.

ML model loading is skipped — tests cover engine logic that doesn't require
a loaded model (properties, voice resolution, WAV header generation).
"""

from __future__ import annotations

import io
import struct
from unittest.mock import MagicMock, patch

import pytest

from dolores_tts.engines.coqui_xtts import CoquiXTTSEngine
from dolores_tts.engines.coqui_xtts import _write_wav_header as _coqui_write_wav_header
from dolores_tts.engines.f5_tts import F5TTSEngine
from dolores_tts.engines.f5_tts import _write_wav_header as _f5_write_wav_header

# ---------------------------------------------------------------------------
# _coqui_write_wav_header (shared logic, tested once here)
# ---------------------------------------------------------------------------

class TestWriteWavHeader:
    def _parse_header(self, data: bytes) -> dict:
        """Parse a 44-byte WAV header into named fields."""
        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WAVE"
        assert data[12:16] == b"fmt "
        assert data[36:40] == b"data"
        return {
            "chunk_size": struct.unpack_from("<I", data, 4)[0],
            "fmt_chunk_size": struct.unpack_from("<I", data, 16)[0],
            "audio_format": struct.unpack_from("<H", data, 20)[0],
            "num_channels": struct.unpack_from("<H", data, 22)[0],
            "sample_rate": struct.unpack_from("<I", data, 24)[0],
            "byte_rate": struct.unpack_from("<I", data, 28)[0],
            "block_align": struct.unpack_from("<H", data, 32)[0],
            "bits_per_sample": struct.unpack_from("<H", data, 34)[0],
            "data_size": struct.unpack_from("<I", data, 40)[0],
        }

    def test_header_is_44_bytes(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=100, sample_rate=24000)
        assert len(buf.getvalue()) == 44

    def test_pcm_format(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["audio_format"] == 1  # PCM

    def test_mono_channel(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["num_channels"] == 1

    def test_sample_rate_stored(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=100, sample_rate=16000)
        h = self._parse_header(buf.getvalue())
        assert h["sample_rate"] == 16000

    def test_16bit_samples(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["bits_per_sample"] == 16

    def test_data_size_matches_samples(self):
        num_samples = 1000
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=num_samples, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        # 16-bit mono: 2 bytes per sample
        assert h["data_size"] == num_samples * 2

    def test_chunk_size_is_data_size_plus_36(self):
        buf = io.BytesIO()
        _coqui_write_wav_header(buf, num_samples=500, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["chunk_size"] == h["data_size"] + 36

    def test_coqui_and_f5_implementations_are_identical(self):
        """Both engine copies of _write_wav_header must produce the same bytes."""
        buf_coqui = io.BytesIO()
        buf_f5 = io.BytesIO()
        _coqui_write_wav_header(buf_coqui, num_samples=1000, sample_rate=22050)
        _f5_write_wav_header(buf_f5, num_samples=1000, sample_rate=22050)
        assert buf_coqui.getvalue() == buf_f5.getvalue()


# ---------------------------------------------------------------------------
# CoquiXTTSEngine
# ---------------------------------------------------------------------------

class TestCoquiXTTSEngine:
    def test_name(self):
        engine = CoquiXTTSEngine()
        assert engine.name == "coqui_xtts"

    def test_not_loaded_initially(self):
        engine = CoquiXTTSEngine()
        assert engine.is_loaded is False

    def test_synthesize_raises_when_not_loaded(self):
        engine = CoquiXTTSEngine()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.synthesize("Hello")

    def test_list_voices_default_only_when_dir_missing(self, tmp_path):
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "nonexistent"))
        voices = engine.list_voices()
        assert voices == ["default"]

    def test_list_voices_includes_wav_dirs(self, tmp_path):
        voice_dir = tmp_path / "abc12345"
        voice_dir.mkdir()
        (voice_dir / "reference.wav").write_bytes(b"fake")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        voices = engine.list_voices()
        assert "default" in voices
        assert "abc12345" in voices

    def test_list_voices_skips_dirs_without_wav(self, tmp_path):
        empty_dir = tmp_path / "empty_voice"
        empty_dir.mkdir()

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        voices = engine.list_voices()
        assert "empty_voice" not in voices

    def test_resolve_voice_default_returns_none(self, tmp_path):
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("default") is None

    def test_resolve_voice_missing_dir_returns_none(self, tmp_path):
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("nonexistent") is None

    def test_resolve_voice_dir_without_wav_returns_none(self, tmp_path):
        voice_dir = tmp_path / "myvoice"
        voice_dir.mkdir()
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("myvoice") is None

    def test_resolve_voice_returns_wav_path(self, tmp_path):
        voice_dir = tmp_path / "myvoice"
        voice_dir.mkdir()
        wav = voice_dir / "reference.wav"
        wav.write_bytes(b"fake_wav")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        result = engine._resolve_voice("myvoice")
        assert result == str(wav)

    def test_synthesize_with_mocked_model(self, tmp_path):
        """Verify synthesize() produces valid WAV bytes when model is mocked."""
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"

        fake_audio = [0.1, 0.2, -0.1, 0.0] * 100  # float list like TTS returns
        engine._model.tts.return_value = fake_audio

        wav_bytes = engine.synthesize("Hello world", voice_id="default")

        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"
        assert len(wav_bytes) > 44  # header + audio data

    def test_synthesize_uses_speaker_wav_when_voice_resolved(self, tmp_path):
        """When a voice profile exists, speaker_wav is passed to TTS model."""
        voice_dir = tmp_path / "myvoice"
        voice_dir.mkdir()
        (voice_dir / "reference.wav").write_bytes(b"fake")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="myvoice")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert "speaker_wav" in call_kwargs
        assert "speaker" not in call_kwargs

    def test_synthesize_uses_default_speaker_when_no_voice(self, tmp_path):
        """When voice_id is 'default', speaker name is used instead of wav."""
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path))
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="default")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker"] == "Ana Florence"
        assert "speaker_wav" not in call_kwargs


# ---------------------------------------------------------------------------
# F5TTSEngine
# ---------------------------------------------------------------------------

class TestF5TTSEngine:
    def test_name(self):
        engine = F5TTSEngine()
        assert engine.name == "f5_tts"

    def test_not_loaded_initially(self):
        engine = F5TTSEngine()
        assert engine.is_loaded is False

    def test_load_sets_loaded_when_mlx_available(self):
        engine = F5TTSEngine()
        mock_mx = MagicMock()
        mock_mx.metal.is_available.return_value = True

        with patch.dict("sys.modules", {"f5_tts_mlx": MagicMock(), "mlx": MagicMock(), "mlx.core": mock_mx}):
            engine.load()

        assert engine.is_loaded is True

    def test_load_stays_unloaded_when_import_fails(self):
        engine = F5TTSEngine()
        # Setting a module to None in sys.modules causes ImportError on import
        with patch.dict("sys.modules", {"f5_tts_mlx": None}):
            engine.load()
        assert engine.is_loaded is False

    def test_synthesize_raises_when_not_loaded(self):
        engine = F5TTSEngine()
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.synthesize("Hello")

    def test_list_voices_default_only_when_dir_missing(self, tmp_path):
        engine = F5TTSEngine(voices_dir=str(tmp_path / "nonexistent"))
        assert engine.list_voices() == ["default"]

    def test_list_voices_includes_dirs_with_reference_wav(self, tmp_path):
        voice_dir = tmp_path / "voice1"
        voice_dir.mkdir()
        (voice_dir / "reference.wav").write_bytes(b"fake")

        engine = F5TTSEngine(voices_dir=str(tmp_path))
        voices = engine.list_voices()
        assert "default" in voices
        assert "voice1" in voices

    def test_list_voices_skips_dirs_without_reference_wav(self, tmp_path):
        empty_dir = tmp_path / "no_wav"
        empty_dir.mkdir()

        engine = F5TTSEngine(voices_dir=str(tmp_path))
        assert "no_wav" not in engine.list_voices()

    def test_resolve_voice_default_returns_none(self, tmp_path):
        engine = F5TTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("default") is None

    def test_resolve_voice_missing_returns_none(self, tmp_path):
        engine = F5TTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("ghost") is None

    def test_resolve_voice_returns_path_when_exists(self, tmp_path):
        voice_dir = tmp_path / "myvoice"
        voice_dir.mkdir()
        wav = voice_dir / "reference.wav"
        wav.write_bytes(b"fake")

        engine = F5TTSEngine(voices_dir=str(tmp_path))
        assert engine._resolve_voice("myvoice") == str(wav)

    def test_synthesize_with_mocked_generate(self, tmp_path):
        """Verify synthesize() produces valid WAV bytes when generate() is mocked."""
        import numpy as np

        engine = F5TTSEngine(voices_dir=str(tmp_path))
        engine._loaded = True

        fake_audio = np.zeros(200, dtype=np.float32)
        mock_generate_fn = MagicMock(return_value=fake_audio)
        mock_generate_module = MagicMock()
        mock_generate_module.generate = mock_generate_fn

        # Patch the submodule so `from f5_tts_mlx.generate import generate` resolves
        with patch.dict("sys.modules", {
            "f5_tts_mlx": MagicMock(),
            "f5_tts_mlx.generate": mock_generate_module,
        }):
            wav_bytes = engine.synthesize("Hello world", voice_id="default")

        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"
        assert len(wav_bytes) > 44
