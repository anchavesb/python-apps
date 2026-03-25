"""Audio recording, conversion, and playback utilities."""

from __future__ import annotations

import asyncio
import io
import queue
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    """Push-to-talk microphone recorder using sounddevice."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._recording = False

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            pass  # ignore overflow warnings
        self._queue.put(indata.copy())

    def start(self) -> None:
        """Start recording from the microphone."""
        self._queue = queue.Queue()
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Stop recording and return raw PCM bytes."""
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        chunks = []
        while not self._queue.empty():
            chunks.append(self._queue.get())

        if not chunks:
            return b""

        audio = np.concatenate(chunks, axis=0)
        return audio.tobytes()


async def pcm_to_webm(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """Convert raw PCM s16le audio to WebM/Opus via ffmpeg."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(pcm_data)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {stderr.decode()}")
    return stdout


class AudioPlayer:
    """Queue-based WAV audio playback using sounddevice."""

    async def play(self, wav_data: bytes) -> None:
        """Play WAV audio data. Blocks until playback finishes."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_sync, wav_data)

    def _play_sync(self, wav_data: bytes) -> None:
        """Synchronous playback."""
        buf = io.BytesIO(wav_data)
        try:
            data, samplerate = sf.read(buf, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()
        except Exception:
            pass  # skip unplayable audio
