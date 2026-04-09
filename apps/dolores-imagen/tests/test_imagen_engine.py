"""Tests for ImageGenProvider ABC interface compliance.

ML model loading is never triggered — tests use a mock concrete provider
to verify the ABC contract and interface requirements.
"""

from __future__ import annotations

import pytest
from dolores_imagen.engine import ImageGenProvider


class MockImageGenProvider(ImageGenProvider):
    """Minimal concrete implementation for ABC compliance testing."""

    def __init__(self) -> None:
        self._loaded = False

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class TestImageGenProviderABC:
    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            ImageGenProvider()  # type: ignore[abstract]

    def test_mock_provider_instantiates(self):
        provider = MockImageGenProvider()
        assert provider is not None

    def test_is_subclass_of_abc(self):
        assert issubclass(MockImageGenProvider, ImageGenProvider)

    def test_name_property(self):
        provider = MockImageGenProvider()
        assert provider.name == "mock"

    def test_is_loaded_false_before_load(self):
        provider = MockImageGenProvider()
        assert provider.is_loaded is False

    def test_load_sets_is_loaded(self):
        provider = MockImageGenProvider()
        provider.load()
        assert provider.is_loaded is True

    def test_generate_returns_bytes(self):
        provider = MockImageGenProvider()
        provider.load()
        result = provider.generate("a red fox")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_generate_accepts_width_height(self):
        provider = MockImageGenProvider()
        provider.load()
        result = provider.generate("a red fox", width=256, height=256)
        assert isinstance(result, bytes)

    def test_generate_default_dimensions(self):
        """generate() must work with only prompt argument."""
        provider = MockImageGenProvider()
        provider.load()
        result = provider.generate("test prompt")
        assert isinstance(result, bytes)
