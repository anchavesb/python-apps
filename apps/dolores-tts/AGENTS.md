# AGENTS.md - dolores-tts (Text-to-Speech)

Text-to-Speech synthesis service for the Dolores assistant.

## Project Overview
- **Role:** Synthesis of natural-sounding speech from text responses.
- **Tech Stack:** FastAPI, `coqui-tts` (XTTS v2), `torch`.

## Build and Setup
- **System Deps:** `ffmpeg`, `libsndfile1`, `torch` with CUDA.
- **Inference:** Uses Coqui XTTS v2 model with local speaker embeddings.
- **Docker:** Use `Dockerfile.gpu`.

## Testing Instructions
- **Run TTS tests:** `pytest apps/dolores-tts/` (repo root).

## Core Logic
- `main.py`: Entry point for speech synthesis API.
- `model.py`: Model loading and inference management.

## Style Guidelines
- **Dolores Common:** Re-use auth and logging logic from `dolores-common`.
- **Latency First:** Keep synthesis chunking in mind for real-time responses.
- **Audio Formats:** Outputs `.wav` (PCM 16-bit, 24kHz) by default.

## Quality Gates
Every code change must pass before merging:
- **Lint:** `make lint` (`ruff check .` — zero errors required)
- **Tests:** `make test` (all tests must pass)

## Deployment Notes
- This service requires significant VRAM (GPU) for low-latency output.
- Check `Dockerfile.gpu` for specific CUDA architecture requirements.
