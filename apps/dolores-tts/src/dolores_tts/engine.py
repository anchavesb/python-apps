"""Abstract TTS engine interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSEngine(ABC):
    """Base class for TTS backends."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def load(self) -> None:
        """Load the model. Call once at startup."""
        ...

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        sample_rate: int = 24000,
    ) -> bytes:
        """Synthesize text to WAV audio bytes (16-bit PCM)."""
        ...

    @abstractmethod
    def list_voices(self) -> list[str]:
        """Return available voice IDs."""
        ...
