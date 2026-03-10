# AGENTS.md - dolores-common (Shared Core)

Shared utility library for all `dolores-*` applications.

## Project Overview
- **Role:** Centralizing auth, logging, models, and shared configs.
- **Tech Stack:** Pydantic, Structlog, FastAPI (common parts).

## Build and Setup
- **Install (from the root):** `make install-common`.
- **Packaging:** Uses `pyproject.toml` and `setuptools`.

## Core Modules (Use these!)
- `auth.py`: Common authentication decorators and checks.
- `logging.py`: Unified `structlog` setup. Use this for all repo logging.
- `models/`: Shared Pydantic data schemas/base models.
- `health.py`: Standard health check health routes for FastAPI.
- `config.py`: Environment variable management and validation.

## Testing Instructions
- **Run library tests:** `pytest libs/dolores-common/` (repo root).
- Ensure all downstream `dolores-*` apps still pass tests after changing `common`.

## Code Style
- **Backward Compatibility:** Changing logic here can break multiple apps. Always check for downstream impacts.
- **Pydantic V2:** Use strictly Pydantic V2 features and runes.
- **No Heavy Deps:** Avoid adding ML or UI dependencies here. Keep it core and lightweight.

## Contribution Guidelines
- Adding a model here implies it will be used by **at least two** different Dolores services.
- Update `__init__.py` to expose common utilities for easier imports.
