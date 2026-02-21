"""faster-whisper model wrapper for speech-to-text."""

from __future__ import annotations

import io
import tempfile
import time
from pathlib import Path

from dolores_common.logging import get_logger

log = get_logger(__name__)

# Supported audio MIME types and their file extensions
SUPPORTED_FORMATS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/flac": ".flac",
    "application/octet-stream": ".wav",  # fallback
}


class STTEngine:
    """Wraps faster-whisper for transcription."""

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 5,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads
        self._beam_size = beam_size
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load the faster-whisper model. Call once at startup."""
        from faster_whisper import WhisperModel

        log.info(
            "loading_model",
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        start = time.monotonic()

        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            cpu_threads=self._cpu_threads,
        )

        elapsed = round(time.monotonic() - start, 2)
        log.info("model_loaded", elapsed_seconds=elapsed)

    def transcribe(
        self,
        audio_data: bytes,
        content_type: str = "audio/wav",
        language: str | None = None,
    ) -> dict:
        """Transcribe audio bytes and return result dict.

        Returns dict with: text, segments, language, language_probability,
        duration_seconds, processing_time_ms
        """
        if not self._model:
            raise RuntimeError("Model not loaded. Call load() first.")

        start = time.monotonic()

        # Write audio to a temp file (faster-whisper needs a file path or file-like)
        ext = SUPPORTED_FORMATS.get(content_type, ".wav")
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = Path(tmp.name)

        try:
            kwargs: dict = {"beam_size": self._beam_size}
            if language:
                kwargs["language"] = language

            segments_iter, info = self._model.transcribe(str(tmp_path), **kwargs)

            segments = []
            full_text_parts = []
            for seg in segments_iter:
                segments.append(
                    {
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "text": seg.text.strip(),
                        "avg_logprob": round(seg.avg_logprob, 4) if seg.avg_logprob else None,
                        "no_speech_prob": round(seg.no_speech_prob, 4) if seg.no_speech_prob else None,
                    }
                )
                full_text_parts.append(seg.text.strip())
        finally:
            tmp_path.unlink(missing_ok=True)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        full_text = " ".join(full_text_parts)

        log.info(
            "transcription_complete",
            language=info.language,
            duration_seconds=round(info.duration, 2),
            processing_time_ms=elapsed_ms,
            text_length=len(full_text),
        )

        return {
            "text": full_text,
            "segments": segments,
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "duration_seconds": round(info.duration, 3),
            "processing_time_ms": elapsed_ms,
        }

    def transcribe_stream(
        self,
        audio_data: bytes,
        content_type: str = "audio/wav",
        language: str | None = None,
    ):
        """Generator that yields partial transcription segments as they are produced.

        Yields dicts with: type ("partial"|"final"), text, language
        """
        if not self._model:
            raise RuntimeError("Model not loaded. Call load() first.")

        ext = SUPPORTED_FORMATS.get(content_type, ".wav")
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = Path(tmp.name)

        try:
            kwargs: dict = {"beam_size": self._beam_size}
            if language:
                kwargs["language"] = language

            segments_iter, info = self._model.transcribe(str(tmp_path), **kwargs)

            full_text_parts = []
            for seg in segments_iter:
                text = seg.text.strip()
                full_text_parts.append(text)
                yield {"type": "partial", "text": text, "language": info.language}

            yield {
                "type": "final",
                "text": " ".join(full_text_parts),
                "language": info.language,
            }
        finally:
            tmp_path.unlink(missing_ok=True)
