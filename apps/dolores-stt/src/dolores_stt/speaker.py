"""Speaker identification using resemblyzer voice embeddings."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from dolores_common.logging import get_logger

from .speaker_store import SpeakerStore

log = get_logger(__name__)


def _convert_to_wav(audio_data: bytes, content_type: str) -> Path:
    """Convert audio bytes to 16kHz mono WAV via ffmpeg."""
    ext_map = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/wave": ".wav",
        "application/octet-stream": ".wav",
    }
    in_ext = ext_map.get(content_type.split(";")[0].strip(), ".webm")

    in_path = Path(tempfile.mktemp(suffix=in_ext))
    out_path = Path(tempfile.mktemp(suffix=".wav"))

    try:
        in_path.write_bytes(audio_data)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(in_path),
                "-ar", "16000", "-ac", "1", "-f", "wav",
                str(out_path),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return out_path
    finally:
        in_path.unlink(missing_ok=True)


class SpeakerIdentifier:
    """Extract voice embeddings and identify speakers."""

    def __init__(self, db_path: str, threshold: float = 0.85) -> None:
        self.store = SpeakerStore(db_path)
        self.threshold = threshold
        self._encoder = None

    def load(self) -> None:
        """Initialize the voice encoder and open the database."""
        from resemblyzer import VoiceEncoder

        log.info("loading_speaker_model")
        self._encoder = VoiceEncoder("cpu")
        self.store.open()
        log.info("speaker_model_loaded")

    def close(self) -> None:
        self.store.close()

    @property
    def encoder(self):
        if self._encoder is None:
            raise RuntimeError("SpeakerIdentifier not loaded")
        return self._encoder

    def extract_embedding(self, wav_path: Path) -> np.ndarray:
        """Extract a 256-dim embedding from a WAV file."""
        from resemblyzer import preprocess_wav

        wav = preprocess_wav(wav_path)
        return self.encoder.embed_utterance(wav)

    def identify(self, audio_data: bytes, content_type: str = "audio/webm") -> dict:
        """Identify the speaker from raw audio data.

        Returns dict with speaker_id, speaker_name, confidence.
        """
        wav_path = _convert_to_wav(audio_data, content_type)
        try:
            embedding = self.extract_embedding(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)

        profiles = self.store.list_with_embeddings()
        if not profiles:
            return {"speaker_id": None, "speaker_name": None, "confidence": 0.0}

        best_id, best_name, best_score = None, None, 0.0
        for p in profiles:
            score = float(
                np.dot(embedding, p["embedding"])
                / (np.linalg.norm(embedding) * np.linalg.norm(p["embedding"]))
            )
            if score > best_score:
                best_id, best_name, best_score = p["id"], p["name"], score

        if best_score >= self.threshold:
            return {"speaker_id": best_id, "speaker_name": best_name, "confidence": best_score}
        return {"speaker_id": None, "speaker_name": None, "confidence": best_score}

    def enroll(
        self,
        name: str,
        audio_samples: list[tuple[bytes, str]],
        email: str | None = None,
    ) -> dict:
        """Enroll a new speaker from audio samples.

        audio_samples: list of (audio_data, content_type) tuples.
        """
        embeddings = []
        for audio_data, content_type in audio_samples:
            wav_path = _convert_to_wav(audio_data, content_type)
            try:
                emb = self.extract_embedding(wav_path)
                embeddings.append(emb)
            finally:
                wav_path.unlink(missing_ok=True)

        if not embeddings:
            raise ValueError("No valid audio samples provided")

        return self.store.enroll(name=name, embeddings=embeddings, email=email)
