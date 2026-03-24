# AGENTS.md - python-apps Monorepo

Welcome! This is the root of the `python-apps` monorepo, a collection of services, libraries, and clients centered around the **Dolores AI Assistant**.

## Project Overview
This repository uses a monorepo structure where shared logic is centralized in `libs/` and specific services/clients are located in `apps/`.
- **Primary stack:** Python 3.12, FastAPI, Svelte 5 (frontend).
- **Orchestration:** Docker and a central `Makefile`.

## Setup Commands
- **Create environment:** `make venv` or `python3.12 -m venv .venv`
- **Install everything:** `make install-all` (Note: This installs all libs and apps in editable mode).
- **Clean environment:** `make clean`

## Testing Instructions
- **Run all tests:** `make test` or `pytest` from the root.
- The root `pytest.ini` and `conftest.py` manage the `pythonpath` for the monorepo.

## Code Style & Conventions
- **Shared Utils:** Always check `libs/dolores-common` before implementing auth, logging, or core models.
- **Logging:** Use `structlog` via the `dolores_common.logging` utility.
- **Async First:** Most services are FastAPI/Async-based. Use `httpx` for requests.
- **Typing:** Strict typing with Pydantic and Type Hints is preferred.

## Repository Structure
- `apps/`: Individual applications (FastAPI services, CLI, Svelte frontend).
- `libs/`: Shared Python libraries used across services.
- `scripts/`: Development and deployment helper scripts.

## Guidance for Nested Projects
Each application in `apps/` has its own `AGENTS.md` with specific instructions. Always prioritize the instructions in the directory where you are working.

<!-- rp1:start -->
## rp1 Knowledge Base

**Use Progressive Disclosure Pattern**

Location: `.rp1/context/`

Files:
- index.md (always load first)
- architecture.md
- modules.md
- patterns.md
- concept_map.md

Loading rules:
1. Always read index.md first.
2. Then load based on task type:
   - Code review: patterns.md
   - Bug investigation: architecture.md, modules.md
   - Feature work: modules.md, patterns.md
   - Strategic or system-wide analysis: all files
<!-- rp1:end -->
