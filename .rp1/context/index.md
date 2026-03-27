# python-apps - Knowledge Base

**Type**: Monorepo
**Languages**: Python, TypeScript, Svelte
**Updated**: 2026-03-24
**Projects**: 10 (dolores-assistant, dolores-brain, dolores-cli, dolores-stt, dolores-tts, dolores-web, todo, portfolio, dolores-common, review-bot)

## Project Summary

`python-apps` is a monorepo containing **Dolores** — a voice-first AI assistant built as five coordinated FastAPI microservices — plus a Flask-based personal productivity app (todo/notes/work-log) that Dolores can control as an auto-discovered tool integration. The system routes voice input through a STT → LLM → TTS pipeline orchestrated by a central WebSocket gateway, with pluggable TTS engines optimized for Apple Silicon and NVIDIA GPU hardware.

## Quick Reference

| Aspect | Value |
|--------|-------|
| Entry Point | `apps/dolores-assistant/src/dolores_assistant/main.py` (WS :8000) |
| Key Pattern | Orchestrated Microservices + OpenAPI-Driven Tool Discovery |
| Tech Stack | Python/FastAPI, Svelte/TypeScript, LiteLLM, faster-whisper, Coqui XTTS / F5-TTS MLX |

## Projects Overview

| Project | Purpose | Language | Entry Point |
|---------|---------|----------|-------------|
| dolores-assistant | WebSocket gateway + STT→Brain→TTS pipeline orchestrator | Python | `main.py` :8000 |
| dolores-brain | LLM inference via LiteLLM (Ollama/Anthropic/OpenAI) | Python | `main.py` :8003 |
| dolores-stt | Speech transcription + speaker identification | Python | `main.py` :8001 |
| dolores-tts | Text-to-speech synthesis (XTTS/F5-TTS/Piper) | Python | `main.py` :8002 |
| dolores-cli | Terminal voice/text chat client | Python | `__main__.py` |
| dolores-web | Svelte SPA with avatar, voice, OIDC auth | TypeScript/Svelte | `src/main.ts` :8080 |
| todo | Flask REST API for todos/notes/work + web UI | Python | `__main__.py` :5000 |
| portfolio | Static personal portfolio site | HTML/JS | `src/index.html` |
| dolores-common | Shared FastAPI utilities (auth, health, logging) | Python | library |
| review-bot | Automated PR review bot via GitHub API polling + LLM | Python | `main.py` :8004 |

## KB File Manifest

**Progressive Loading**: Load files on-demand based on your task.

| File | Lines | Load For |
|------|-------|----------|
| architecture.md | ~197 | System design, deployment, service ports, data flows, security |
| modules.md | ~231 | Component breakdown, module responsibilities, dependency graph |
| patterns.md | ~94 | Code conventions, error handling, async patterns, DI |
| concept_map.md | ~130 | Domain terminology, entity definitions, bounded contexts |

## Task-Based Loading

| Task | Files to Load |
|------|---------------|
| Code review | `patterns.md` |
| Bug investigation | `architecture.md`, `modules.md` |
| Feature implementation | `modules.md`, `patterns.md` |
| Adding a tool integration | `concept_map.md`, `modules.md` |
| Security audit | `architecture.md`, `concept_map.md` |
| Strategic analysis | ALL files |

## How to Load

```
Read: /Users/achaves/repos/python-apps/.rp1/context/{filename}
```

## Repository Structure

```
python-apps/
├── apps/
│   ├── dolores-assistant/   # Orchestrator (WebSocket gateway, tool loop)
│   ├── dolores-brain/       # LLM inference service
│   ├── dolores-stt/         # Speech-to-text service
│   ├── dolores-tts/         # Text-to-speech service
│   ├── dolores-cli/         # Terminal client
│   ├── dolores-web/         # Svelte SPA frontend
│   ├── todo/                # Flask productivity app (tool integration)
│   └── portfolio/           # Static portfolio site
├── libs/
│   └── dolores-common/      # Shared FastAPI utilities
├── docker/                  # Shared Dockerfiles (GPU base)
├── scripts/                 # Setup and dev scripts
├── docker-compose.yml       # Hybrid native/docker orchestration
└── Makefile                 # Build, test, GPU targets
```

## Navigation

- **[architecture.md](architecture.md)**: System design, deployment topology, data flows, security
- **[modules.md](modules.md)**: Component breakdown, module responsibilities, dependency graph
- **[patterns.md](patterns.md)**: Code conventions, error handling, async/DI/extension patterns
- **[concept_map.md](concept_map.md)**: Domain terminology, entity definitions, bounded contexts
