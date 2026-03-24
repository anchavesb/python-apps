"""Dolores TTS service."""

import os

# Set MPS fallback for PyTorch on macOS - MUST be before torch is imported
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

__version__ = "0.2.2"
