# AGENTS.md - dolores-brain (LLM Logic)

This application is the intelligence layer of the Dolores AI assistant.

## Project Overview
- **Role:** Multi-provider LLM routing and core application logic.
- **Tech Stack:** FastAPI, LiteLLM, aiosqlite (for conversation storage).
- **Router logic:** Specialized in `provider_config.py` using `LiteLLM`.

## Setup and Run Commands
- **Install (from the root):** `make install-brain`
- **Run (dev):** `uvicorn dolores_brain.main:app` or `python -m dolores_brain`
- **Config:** Managed via `.env` (API keys for providers).

## Architecture
- `conversation.py`: Manages the flow of user/assistant turns.
- `provider_config.py`: LiteLLM adapters and multi-service fallback.
- `models/`: Database models for persisting history.

## Testing Instructions
- **Run brain tests:** `pytest apps/dolores-brain/` (from repo root).
- Always mock LLM provider calls in tests!

## Code Style
- **Dolores Common:** Heavily depends on `dolores-common` for models and logging.
- **Async DB:** Use `aiosqlite` or async SQLAlchemy patterns.
- **Provider Abstraction:** Don't write provider-specific logic in routes; use the `LiteLLM` interface.

## PR Instructions
- Check that new LLM response schemas are added to `schemas.py`.
- Run `make test` before pushing.
