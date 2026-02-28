"""Coqui XTTS v2 TTS backend.

IMPORTANT: Must run with a single uvicorn worker due to CUDA/torch forking issues.
"""

from __future__ import annotations

import io
import struct
import time
from pathlib import Path

from dolores_common.logging import get_logger

from ..engine import TTSEngine

log = get_logger(__name__)


def _write_wav_header(f: io.BytesIO, num_samples: int, sample_rate: int, num_channels: int = 1, bits_per_sample: int = 16) -> None:
    """Write a WAV file header."""
    data_size = num_samples * num_channels * (bits_per_sample // 8)
    f.write(b"RIFF")
    f.write(struct.pack("<I", 36 + data_size))
    f.write(b"WAVE")
    f.write(b"fmt ")
    f.write(struct.pack("<I", 16))  # chunk size
    f.write(struct.pack("<H", 1))   # PCM format
    f.write(struct.pack("<H", num_channels))
    f.write(struct.pack("<I", sample_rate))
    f.write(struct.pack("<I", sample_rate * num_channels * (bits_per_sample // 8)))
    f.write(struct.pack("<H", num_channels * (bits_per_sample // 8)))
    f.write(struct.pack("<H", bits_per_sample))
    f.write(b"data")
    f.write(struct.pack("<I", data_size))


class CoquiXTTSEngine(TTSEngine):
    """Coqui XTTS v2 TTS engine with voice cloning support."""

    def __init__(self, device: str = "auto", voices_dir: str = "data/voices") -> None:
        self._device = device
        self._voices_dir = Path(voices_dir)
        self._model = None
        self._config = None

    @property
    def name(self) -> str:
        return "coqui_xtts"

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load XTTS v2 model."""
        from TTS.api import TTS

        log.info("loading_tts_model", engine="coqui_xtts", device=self._device)
        start = time.monotonic()

        device = self._device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        self._voices_dir.mkdir(parents=True, exist_ok=True)

        # Pick the first available built-in speaker for default voice
        speakers = getattr(self._model, "speakers", None) or []
        self._default_speaker = speakers[0] if speakers else "Ana Florence"

        elapsed = round(time.monotonic() - start, 2)
        log.info("tts_model_loaded", engine="coqui_xtts", device=device, elapsed_seconds=elapsed, default_speaker=self._default_speaker)

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        sample_rate: int = 24000,
    ) -> bytes:
        """Synthesize text to WAV bytes using XTTS v2."""
        if not self._model:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Resolve voice reference audio
        speaker_wav = self._resolve_voice(voice_id)

        start = time.monotonic()
        tts_kwargs: dict = {"text": text, "language": "en"}
        if speaker_wav:
            tts_kwargs["speaker_wav"] = speaker_wav
        else:
            tts_kwargs["speaker"] = self._default_speaker

        wav_list = self._model.tts(**tts_kwargs)

        # Convert float list to 16-bit PCM WAV bytes
        import numpy as np
        wav_array = np.array(wav_list, dtype=np.float32)
        wav_array = np.clip(wav_array, -1.0, 1.0)
        pcm_data = (wav_array * 32767).astype(np.int16).tobytes()

        buf = io.BytesIO()
        _write_wav_header(buf, len(wav_array), sample_rate)
        buf.write(pcm_data)

        elapsed = round(time.monotonic() - start, 2)
        log.info("synthesis_complete", voice_id=voice_id, text_length=len(text), elapsed_seconds=elapsed)

        return buf.getvalue()

    def list_voices(self) -> list[str]:
        """List available voice profiles (directory names in voices_dir)."""
        voices = ["default"]
        if self._voices_dir.exists():
            for d in self._voices_dir.iterdir():
                if d.is_dir() and any(d.glob("*.wav")):
                    voices.append(d.name)
        return voices

    def _resolve_voice(self, voice_id: str) -> str | None:
        """Resolve a voice_id to a reference WAV file path."""
        if voice_id == "default":
            return None  # XTTS uses its own default speaker

        voice_dir = self._voices_dir / voice_id
        if not voice_dir.exists():
            log.warning("voice_not_found", voice_id=voice_id)
            return None

        # Use the first WAV file in the voice directory
        wavs = list(voice_dir.glob("*.wav"))
        if not wavs:
            log.warning("no_reference_audio", voice_id=voice_id)
            return None

        return str(wavs[0])
