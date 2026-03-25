"""F5-TTS MLX engine for high-performance voice cloning on Apple Silicon."""

from __future__ import annotations

import io
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from dolores_common.logging import get_logger

from ..engine import TTSEngine
from .audio_utils import write_wav_header

log = get_logger(__name__)


def _ensure_24khz(path: str) -> str:
    """Return a path to a 24kHz WAV version of the audio, resampling via ffmpeg if needed."""
    info = sf.info(path)
    if info.samplerate == 24000:
        return path
    log.warning("ref_audio_wrong_samplerate", path=path, samplerate=info.samplerate, resampling=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-ar", "24000", "-ac", "1", "-acodec", "pcm_s16le", tmp.name],
        capture_output=True,
        check=True,
    )
    return tmp.name


class F5TTSEngine(TTSEngine):
    """F5-TTS engine using MLX for Apple Silicon."""

    def __init__(self, voices_dir: str = "data/voices") -> None:
        self._voices_dir = Path(voices_dir)
        self._loaded = False

    @property
    def name(self) -> str:
        return "f5_tts"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        """Verify that f5-tts-mlx is available."""
        try:
            import f5_tts_mlx  # noqa: F401
            import mlx.core as mx
            if not mx.metal.is_available():
                 log.warning("f5_tts_mlx_no_metal", msg="MLX is available but Metal (GPU) is not detected.")
            self._loaded = True
            log.info("f5_tts_mlx_loaded")
        except ImportError:
            log.error("f5_tts_mlx_not_installed", msg="f5-tts-mlx is not installed. Install with 'pip install f5-tts-mlx'")
            self._loaded = False

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        sample_rate: int = 24000,
        ref_text: str | None = None,
    ) -> bytes:
        """Synthesize text using F5-TTS MLX."""
        if not self._loaded:
            raise RuntimeError("F5-TTS MLX not loaded or not installed.")

        from f5_tts_mlx.generate import generate

        # Resolve voice reference audio and ensure it's at 24kHz
        speaker_wav = self._resolve_voice(voice_id)
        if speaker_wav:
            speaker_wav = _ensure_24khz(speaker_wav)

        # F5-TTS works best with a reference transcript.
        # If not provided, it might try to auto-transcribe or fail depending on version.
        # We prefer the one stored in the DB.
        if not ref_text:
            log.warning("f5_tts_missing_ref_text", voice_id=voice_id)
            ref_text = "" # fallback to empty string if missing

        start = time.monotonic()

        # generate() returns a numpy array (usually float32)
        # Note: ref_audio can be a path string
        audio_array = generate(
            generation_text=text,
            ref_audio_path=speaker_wav if speaker_wav else None,
            ref_audio_text=ref_text if speaker_wav else "",
        )

        # Convert to 16-bit PCM
        audio_array = np.clip(audio_array, -1.0, 1.0)
        pcm_data = (audio_array * 32767).astype(np.int16).tobytes()

        buf = io.BytesIO()
        write_wav_header(buf, len(audio_array), sample_rate)
        buf.write(pcm_data)

        elapsed = round(time.monotonic() - start, 2)
        log.info("f5_tts_synthesis_complete", voice_id=voice_id, elapsed_seconds=elapsed)

        return buf.getvalue()

    def list_voices(self) -> list[str]:
        """List available voice profiles."""
        voices = ["default"]
        if self._voices_dir.exists():
            for d in self._voices_dir.iterdir():
                if d.is_dir() and (d / "reference.wav").exists():
                    voices.append(d.name)
        return voices

    def _resolve_voice(self, voice_id: str) -> str | None:
        """Resolve a voice_id to a reference WAV file path."""
        if voice_id == "default":
            return None

        voice_dir = self._voices_dir / voice_id
        ref_wav = voice_dir / "reference.wav"
        if ref_wav.exists():
            return str(ref_wav)

        return None
