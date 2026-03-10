# AGENTS.md - dolores-assistant (Orchestrator)

This application coordinates the Dolores AI pipeline (STT -> Brain -> TTS).

## Project Overview
- **Role:** Main coordinator for assistant service interactions.
- **Tech Stack:** FastAPI, Async WebSockets, HTTPX.
- **Core logic:** High-level pipeline management in `pipeline.py`.

## Build and Run Commands
- **Install (from the root):** `make install-assistant`
- **Run (dev):** `uvicorn dolores_assistant.main:app --reload`
- **Build Docker:** `make docker-build APP=dolores-assistant` (from root).

## Core Modules
- `pipeline.py`: The STT -> Brain -> TTS workflow coordinator.
- `main.py`: Entry point for FastAPI and WebSocket handlers.
- `clients/`: Async clients for downstream services (brain, stt, tts).

## Testing Instructions
- **Run app tests:** `pytest apps/dolores-assistant/` (from repo root).
- Ensure integration mocks are up to date for brain/stt/tts services.

## Code Style
- **Dolores Common:** Re-use auth and logging from `dolores-common`.
- **Asynchronous Flow:** Avoid blocking operations in the audio pipeline.
- **WebSocket Protocol:** Audio is handled as chunked binary/base64 data.

## Security Considerations
- **Auth Middleware:** All API and WebSocket calls must pass common auth checks.
- **Health Checks:** Use the standard `/health` endpoint from `dolores-common`.
