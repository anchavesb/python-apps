"""Piper TTS backend (CPU-only fallback).

Piper is a fast, local text-to-speech system. No voice cloning,
but ~100 MB models and runs well on CPU.
"""

from __future__ import annotations

from dolores_common.logging import get_logger

from ..engine import TTSEngine

log = get_logger(__name__)


class PiperEngine(TTSEngine):
    """Piper TTS engine — CPU-only fallback. Not yet implemented."""

    @property
    def name(self) -> str:
        return "piper"

    @property
    def is_loaded(self) -> bool:
        return False

    def load(self) -> None:
        log.warning("piper_not_implemented", msg="Piper TTS engine is not yet implemented")

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        sample_rate: int = 22050,
    ) -> bytes:
        raise NotImplementedError("Piper TTS is not yet implemented")

    def list_voices(self) -> list[str]:
        return []
