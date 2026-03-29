"""Abstract image generation provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ImageGenProvider(ABC):
    """Base class for image generation backends."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def load(self) -> None:
        """Load model weights. Called once at startup."""
        ...

    @abstractmethod
    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        """Generate image from prompt. Returns PNG bytes."""
        ...
