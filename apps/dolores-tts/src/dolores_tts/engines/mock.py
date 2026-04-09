"""Mock TTS engine for testing."""

from __future__ import annotations

from ..engine import TTSEngine


class MockEngine(TTSEngine):
    """Mock TTS engine that returns static silence/beep."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def supported_emotions(self) -> list[str]:
        return ["neutral"]

    def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        sample_rate: int = 24000,
        ref_text: str | None = None,
        emotion: str | None = None,
    ) -> bytes:
        # Return a tiny valid WAV header + 1 second of silence (or just dummy bytes)
        # This is a minimal 44-byte WAV header for mono 16-bit PCM
        header = (
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            + sample_rate.to_bytes(4, "little")
            + (sample_rate * 2).to_bytes(4, "little")
            + b"\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        return header + b"\x00" * 1000

    def list_voices(self) -> list[str]:
        return ["default"]
