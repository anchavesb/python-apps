# AGENTS.md - dolores-stt (Speech-to-Text)

Speech-to-Text inference service for the Dolores assistant.

## Project Overview
- **Role:** Transcribing audio to text using Whisper models.
- **Tech Stack:** FastAPI, `faster-whisper`, CUDA.

## Build and Setup
- **System Deps:** `ffmpeg`, `libsndfile1`, `CUDA 12.4`.
- **Inference:** Uses Whisper Large-V3 or Medium by default.
- **Docker:** Use `Dockerfile.gpu` for builds with NVIDIA drivers.

## Testing Instructions
- **Run STT tests:** `pytest apps/dolores-stt/` (repo root).
- Use local short audio samples for integration testing.

## Code Style
- **Dolores Common:** Re-use `dolores-common` for standard health and logging.
- **Async Execution:** Inference is wrapped in async executors to avoid blocking.
- **Audio Formats:** Primary support for `.wav` (PCM 16-bit, 16kHz).

## Quality Gates
Every code change must pass before merging:
- **Lint:** `make lint` (`ruff check .` — zero errors required)
- **Tests:** `make test` (all tests must pass)

## Model Loading
- Models are cached in `~/.cache/huggingface` by default.
- Use explicit model tagging in `config.py`.
