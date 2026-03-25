# AGENTS.md - dolores-cli (Terminal UI)

The main terminal client for interacting with the Dolores system.

## Project Overview
- **Role:** Interactive TUI for text and voice-enabled chat.
- **Tech Stack:** `prompt-toolkit`, `rich`, `sounddevice`.
- **Interface:** Terminal-based, supports live audio input/output.

## Build and Run
- **Install (from the root):** `make install-cli`.
- **Run (dev):** `dolores-cli` or `python -m dolores_cli`.

## Core Logic
- `main.py`: Interactive loop and command parsing.
- `audio/`: Logic for recording and playing audio via `sounddevice`.
- `api/`: Clients for `dolores-assistant` WebSocket and HTTP endpoints.

## Testing Instructions
- **Run CLI tests:** `pytest apps/dolores-cli/` (repo root).

## Interface Conventions
- **Rendering:** Use `Rich` for pretty-printing markdown responses.
- **Inputs:** `Prompt-toolkit` handles command history and completion.
- **Dolores Common:** Re-use shared models for API communication.

## Quality Gates
Every code change must pass before merging:
- **Lint:** `make lint` (`ruff check .` — zero errors required)
- **Tests:** `make test` (all tests must pass)

## System Dependencies
- Requires `portaudio` (system) and `libasound2` (Linux) for voice.
- Ensure `ALSA` or `PulseAudio` is properly configured for the terminal environment.
