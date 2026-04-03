"""Tests for TTS engine implementations.

ML model loading is skipped — tests cover engine logic that doesn't require
a loaded model (properties, voice resolution, WAV header generation).
"""

from __future__ import annotations

import io
import struct
from unittest.mock import MagicMock, patch

import pytest

from dolores_tts.engines.audio_utils import write_wav_header
from dolores_tts.engines.coqui_xtts import CoquiXTTSEngine
from dolores_tts.engines.f5_tts import F5TTSEngine
from dolores_tts.engines.piper import PiperEngine

# ---------------------------------------------------------------------------
# write_wav_header (shared utility, tested once)
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
        write_wav_header(buf, num_samples=100, sample_rate=24000)
        assert len(buf.getvalue()) == 44

    def test_pcm_format(self):
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["audio_format"] == 1

    def test_mono_channel(self):
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["num_channels"] == 1

    def test_sample_rate_stored(self):
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=100, sample_rate=16000)
        h = self._parse_header(buf.getvalue())
        assert h["sample_rate"] == 16000

    def test_16bit_samples(self):
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=100, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["bits_per_sample"] == 16

    def test_data_size_matches_samples(self):
        num_samples = 1000
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=num_samples, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        # 16-bit mono: 2 bytes per sample
        assert h["data_size"] == num_samples * 2

    def test_chunk_size_is_data_size_plus_36(self):
        buf = io.BytesIO()
        write_wav_header(buf, num_samples=500, sample_rate=24000)
        h = self._parse_header(buf.getvalue())
        assert h["chunk_size"] == h["data_size"] + 36


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
        import soundfile as sf

        engine = F5TTSEngine(voices_dir=str(tmp_path))
        engine._loaded = True

        fake_audio = np.zeros(200, dtype=np.float32)

        def fake_generate(**kwargs):
            # Write fake audio to the output_path the engine passes
            sf.write(kwargs["output_path"], fake_audio, 24000)

        mock_generate_module = MagicMock()
        mock_generate_module.generate = fake_generate

        # Patch the submodule so `from f5_tts_mlx.generate import generate` resolves
        with patch.dict(
            "sys.modules",
            {
                "f5_tts_mlx": MagicMock(),
                "f5_tts_mlx.generate": mock_generate_module,
            },
        ):
            wav_bytes = engine.synthesize("Hello world", voice_id="default")

        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"
        assert len(wav_bytes) > 44


# ---------------------------------------------------------------------------
# CoquiXTTSEngine — emotion conditioning
# ---------------------------------------------------------------------------


class TestCoquiXTTSEngineEmotionConditioning:
    def test_supported_emotions_empty_when_dir_missing(self, tmp_path):
        engine = CoquiXTTSEngine(emotions_dir=str(tmp_path / "nonexistent"))
        assert engine.supported_emotions() == []

    def test_supported_emotions_returns_loaded_emotions(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        for name in ("happy", "sad", "angry", "neutral"):
            (emotions_dir / f"{name}.wav").write_bytes(b"fake")

        engine = CoquiXTTSEngine(emotions_dir=str(emotions_dir))
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._shared_emotion_refs = engine._load_shared_emotion_refs()

        assert engine.supported_emotions() == ["angry", "happy", "neutral", "sad"]

    def test_synthesize_swaps_speaker_wav_for_shared_clip(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        happy_clip = emotions_dir / "happy.wav"
        happy_clip.write_bytes(b"fake")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "voices"), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {str(k): str(emotions_dir / f"{k}.wav") for k in ("happy",)}
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="default", emotion="happy")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker_wav"] == str(happy_clip)
        assert "speaker" not in call_kwargs

    def test_synthesize_prefers_per_voice_clip_over_shared(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        shared_clip = emotions_dir / "happy.wav"
        shared_clip.write_bytes(b"shared")

        voices_dir = tmp_path / "voices"
        per_voice_dir = voices_dir / "myvoice" / "emotion_refs"
        per_voice_dir.mkdir(parents=True)
        per_voice_clip = per_voice_dir / "happy.wav"
        per_voice_clip.write_bytes(b"per_voice")

        engine = CoquiXTTSEngine(voices_dir=str(voices_dir), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {"happy": str(shared_clip)}
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="myvoice", emotion="happy")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker_wav"] == str(per_voice_clip)

    def test_synthesize_uses_shared_when_no_per_voice(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        shared_clip = emotions_dir / "happy.wav"
        shared_clip.write_bytes(b"shared")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "voices"), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {"happy": str(shared_clip)}
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="default", emotion="happy")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker_wav"] == str(shared_clip)

    def test_synthesize_no_swap_when_no_clip_found(self, tmp_path):
        """When no emotion clip resolves, original speaker kwarg is retained."""
        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "voices"), emotions_dir=str(tmp_path / "nonexistent"))
        engine._shared_emotion_refs = {}
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        with patch("dolores_tts.engines.coqui_xtts.log") as mock_log:
            engine.synthesize("Hello", voice_id="default", emotion="happy")

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker"] == "Ana Florence"
        assert "speaker_wav" not in call_kwargs
        mock_log.warning.assert_called_with("emotion_clip_unavailable", emotion="happy", fallback="voice_default")

    def test_synthesize_no_swap_when_emotion_none(self, tmp_path):
        """emotion=None leaves the original speaker resolution unchanged."""
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        (emotions_dir / "happy.wav").write_bytes(b"fake")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "voices"), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {"happy": str(emotions_dir / "happy.wav")}
        engine._model = MagicMock()
        engine._default_speaker = "Ana Florence"
        engine._model.tts.return_value = [0.0] * 100

        engine.synthesize("Hello", voice_id="default", emotion=None)

        call_kwargs = engine._model.tts.call_args.kwargs
        assert call_kwargs["speaker"] == "Ana Florence"
        assert "speaker_wav" not in call_kwargs

    def test_resolve_emotion_clip_per_voice_priority(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        shared_clip = emotions_dir / "happy.wav"
        shared_clip.write_bytes(b"shared")

        voices_dir = tmp_path / "voices"
        per_voice_dir = voices_dir / "myvoice" / "emotion_refs"
        per_voice_dir.mkdir(parents=True)
        per_voice_clip = per_voice_dir / "happy.wav"
        per_voice_clip.write_bytes(b"per_voice")

        engine = CoquiXTTSEngine(voices_dir=str(voices_dir), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {"happy": str(shared_clip)}

        result = engine._resolve_emotion_clip("myvoice", "happy")
        assert result == str(per_voice_clip)

    def test_resolve_emotion_clip_shared_fallback(self, tmp_path):
        emotions_dir = tmp_path / "emotion_refs"
        emotions_dir.mkdir()
        shared_clip = emotions_dir / "happy.wav"
        shared_clip.write_bytes(b"shared")

        engine = CoquiXTTSEngine(voices_dir=str(tmp_path / "voices"), emotions_dir=str(emotions_dir))
        engine._shared_emotion_refs = {"happy": str(shared_clip)}

        result = engine._resolve_emotion_clip("somevoice", "happy")
        assert result == str(shared_clip)


# ---------------------------------------------------------------------------
# F5TTSEngine — emotion no-op
# ---------------------------------------------------------------------------


class TestF5TTSEngineEmotion:
    def test_supported_emotions_returns_empty(self):
        engine = F5TTSEngine()
        assert engine.supported_emotions() == []

    def test_synthesize_accepts_emotion_kwarg(self, tmp_path):
        """Calling synthesize() with emotion= raises RuntimeError (not loaded), not TypeError."""
        engine = F5TTSEngine()
        with pytest.raises(RuntimeError):
            engine.synthesize("Hello", emotion="happy")


# ---------------------------------------------------------------------------
# PiperEngine — emotion no-op
# ---------------------------------------------------------------------------


class TestPiperEngineEmotion:
    def test_supported_emotions_returns_empty(self):
        engine = PiperEngine()
        assert engine.supported_emotions() == []

    def test_synthesize_accepts_emotion_kwarg(self):
        """Calling synthesize() with emotion= raises NotImplementedError, not TypeError."""
        engine = PiperEngine()
        with pytest.raises(NotImplementedError):
            engine.synthesize("Hello", emotion="happy")
