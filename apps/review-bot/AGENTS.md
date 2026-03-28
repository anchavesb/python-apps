# AGENTS.md - review-bot (Automated GitHub PR Review Service)

This service polls GitHub repositories for open pull requests and posts automated
AI-powered code reviews as GitHub PR review comments.

## Project Overview
- **Role:** Automated PR review bot that fetches diffs, assembles prompts, calls an LLM, and posts structured review comments back to GitHub.
- **Tech Stack:** FastAPI, LiteLLM, aiosqlite, httpx, Pydantic.
- **Trigger sources:** Async polling loop (poller.py) and manual HTTP trigger (routes.py).

## Setup and Run Commands
- **Install (from the root):** `pip install -e apps/review-bot[test]`
- **Run (dev):** `uvicorn review_bot.main:app` or `python -m review_bot`
- **Config:** Environment variables (see README.md for full list). Registry of watched repos lives in `config/repos.yml`.

## Architecture

```
main.py            — FastAPI app lifespan: loads config, starts poller loop
poller.py          — Async polling loop; dispatches run_review() concurrently via asyncio.gather
review_runner.py   — Core pipeline: diff → AGENTS.md discovery → prompt → LLM → parse → post
config.py          — Three-level config precedence (env defaults → repos.yml → per-repo review-bot.yml)
schemas.py         — Shared Pydantic models including EffectiveConfig
github_client.py   — httpx-based GitHub REST API client (list PRs, fetch diffs, post reviews)
agents_discovery.py — Fetches AGENTS.md files relevant to the diff (root + two-level subdir prefix)
prompt.py          — Assembles LiteLLM messages from base prompt, AGENTS.md context, and diff
llm_client.py      — Async LiteLLM wrapper (call_llm)
review_parser.py   — Parses LLM JSON response into ReviewResult with inline comments
state_store.py     — aiosqlite-backed SHA store to avoid duplicate reviews
routes.py          — /review HTTP endpoint for manual trigger
```

### Review Pipeline (run_review)
1. Fetch per-repo `.github/review-bot.yml` (optional Layer 1 config).
2. Resolve `EffectiveConfig` with three-level precedence.
3. Fetch PR diff via GitHub API.
4. Discover relevant AGENTS.md files.
5. Assemble LiteLLM prompt (system + user messages).
6. Call LLM and parse structured JSON response.
7. Post review comments to GitHub Reviews API.
8. Store head SHA to prevent re-reviewing unchanged PRs.

### Concurrency
A module-level `asyncio.Semaphore` (configured via `REVIEW_BOT_MAX_CONCURRENT`) bounds
concurrent LLM calls. `_poll_repo` dispatches all eligible PRs concurrently via
`asyncio.gather`; the semaphore inside `run_review` is what limits actual concurrency.

### Config Precedence (highest → lowest)
1. Per-repo `.github/review-bot.yml` in the target repository
2. Per-repo entry in `config/repos.yml`
3. Global `defaults` in `config/repos.yml`

## Testing Instructions
- **Run all tests:** `pytest apps/review-bot/` (from repo root).
- **Run with coverage:** `pytest --cov=review_bot apps/review-bot/`
- Always mock `litellm.acompletion` and GitHub HTTP calls (use `respx` for integration tests).
- `EffectiveConfig` lives in `schemas.py`; import it from there or from `config` (re-exported).

## Code Style
- All async I/O uses `asyncio`/`httpx`; no blocking calls in the hot path.
- Structured logging via `dolores_common.logging.get_logger`.
- Pydantic models for all data structures; define shared models in `schemas.py`.
- Per-repo YAML keys use `extension` (not `text`) for the prompt fragment field.

## Quality Gates
Every code change must pass before merging:
- **Lint:** `ruff check .` (from repo root) — must return zero errors
- **Tests:** `pytest apps/review-bot/` (all tests must pass)
- **No duplicate model definitions:** `EffectiveConfig` is canonical in `schemas.py`.
