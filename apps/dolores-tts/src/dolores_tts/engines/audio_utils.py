"""Shared audio utilities for TTS engines."""

from __future__ import annotations

import io
import struct


def write_wav_header(
    f: io.BytesIO,
    num_samples: int,
    sample_rate: int,
    num_channels: int = 1,
    bits_per_sample: int = 16,
) -> None:
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
