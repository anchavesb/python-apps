# Implementation Patterns

**Project**: python-apps (Dolores Monorepo)
**Last Updated**: 2026-03-24

## Naming & Organization

**Files**: `snake_case` for Python modules (`pipeline.py`, `voice_profiles.py`, `speaker_store.py`); PascalCase for TypeScript class files (`DoloresClient.ts`). Routes files named `routes.py` per service.

**Functions**: Python — verb-prefixed snake_case (`get_engine`, `set_store`, `load_tools`, `create_voice`). TypeScript — camelCase verbs (`sendText`, `startRecording`, `enqueue`). Private helpers prefixed with `_` (`_validate_tags`, `_atomic_write`, `_trim_history`).

**Imports**: All Python files use `from __future__ import annotations`. Absolute imports within monorepo via package names (`from dolores_common.logging import get_logger`). Relative imports only within the same service package (`from .config import settings`).

---

## Type & Data Modeling

**Data modeling**: Pydantic `BaseModel` for API request/response schemas (`ChatRequest`, `ChatResponse`, `HealthStatus`). Internal domain objects use plain dicts or dataclasses (`Todo`, `Note`, `WorkItem`). TypeScript uses interfaces for data shapes and discriminated unions for event protocols (`MessageEvent`).

**Type strictness**: Strict typing throughout. Python uses `X | None` union syntax (not `Optional[X]`). All functions have return type annotations. TypeScript uses strict interface definitions.

**Immutability**: No frozen dataclasses; mutation is explicit. Svelte state uses `$state<>` rune. Audio queue uses imperative mutation.

---

## Error Handling

**Strategy**: Domain errors raised as exceptions (`ValidationError` subclasses `Exception` in todo). FastAPI routes raise `HTTPException` with appropriate status codes. Service call failures return `None` or empty list — never propagate to caller.

**Propagation**: Catch-at-boundary: service HTTP calls catch all exceptions, log with structured context, return `None`/fallback. FastAPI routes translate `None` returns to 404/502. `asyncio.gather(..., return_exceptions=True)` for parallel calls that must not block each other.

**Common types**: `HTTPException`, `ValidationError`, `RuntimeError`, `PermissionError`, `ValueError`

---

## Validation & Boundaries

**Location**: At API boundary for FastAPI services (content-type checks, size limits, empty-body checks). Domain validation in store layer (`_validate_todo`, `_validate_note` called before writes). Input regex for names (`SPEAKER_NAME_RE`, `_NAME_RE`).

**Method**: Manual validation raising `ValidationError` or `HTTPException`. Pydantic handles schema validation for API models. Magic-byte validation for audio data in WebSocket handler.

---

## Observability

**Logging**: structlog via `dolores_common.logging.get_logger(__name__)`. All log calls use keyword-only structured fields (`log.info('event_name', key=value)`). Request IDs bound to structlog context via middleware. Performance timing logged as `elapsed_seconds` or `processing_time_ms`.

**Metrics**: No metrics framework. Timing via `time.monotonic()` logged as structured fields.

**Tracing**: Request ID propagated via `x-request-id` header; bound to structlog context per request. No distributed tracing (OpenTelemetry/Jaeger).

---

## Testing Idioms

Test files located under `tests/` directories per service (e.g. `apps/dolores-assistant/tests/`). Root-level `pytest.ini` and `conftest.py` configure workspace-wide test discovery.

---

## Quality Gates

**Linter**: `ruff` (configured in `ruff.toml` at repo root). Run via `make lint`. Every code change must pass `ruff check .` with zero errors before merging.

**Rules enforced**: E/W (pycodestyle), F (pyflakes), I (isort). Line length: 120.

**Tests**: All changes must pass `make test` (runs full monorepo test suite via pytest).

**CI**: Both `lint` and `test` jobs run on every PR and push to `main` (`.github/workflows/ci.yml`).

**Pre-commit**: `.pre-commit-config.yaml` runs ruff automatically on `git commit`. Activate locally with `pre-commit install`.

---

## I/O & Integration Patterns

**Database**:
- `aiosqlite` for async services (`ConversationStore`, `VoiceProfileStore`) with explicit `init()`/`close()` lifecycle
- Synchronous `sqlite3` with WAL mode + `asyncio.to_thread()` offloading in `SpeakerStore`
- SQLAlchemy ORM for PostgreSQL multiuser mode (`PostgresStore`)
- Raw SQL strings as module-level constants; schema migration inline via `try/except ALTER TABLE`

**HTTP clients**: `httpx.AsyncClient` for all inter-service HTTP. Single shared client per service, started at app lifespan, closed on shutdown. Timeouts set per-call. GPU-bound services use `asyncio.Semaphore(1)` to serialize concurrent requests.

---

## Concurrency Patterns

**Async usage**: All FastAPI routes are async. CPU/GPU-bound operations offloaded via `asyncio.to_thread()`. Parallel downstream calls use `asyncio.gather(..., return_exceptions=True)`. SSE streaming with async generators. WebSocket handlers accumulate binary chunks in `bytearray`, reset on each utterance.

**Patterns**: GPU concurrency controlled with `asyncio.Semaphore(1)` per GPU service (STT, TTS). `ContextVar` used for per-request user JWT propagation across async call chains (`current_user_token`). ONNX model uses lazy-load singleton with module-level globals (`_session`, `_tokenizer`, `_intent_centroids`).

---

## Dependency Injection

**Injection**: FastAPI `Depends()` for injecting singletons (engine, store, service client). Singletons stored as module-level globals (`_engine`, `_store`) with `set_*()` initializers called from app lifespan. `get_*()` dependency functions raise 503 if not initialized.

**Config**: Pydantic `BaseSettings` via `from .config import settings` singleton per service. Auth credentials read directly from `os.environ` in dolores-common (`DOLORES_SERVICE_PSK`, `DOLORES_API_KEY`). No auth when env var not set (dev-mode bypass).

---

## Extension Patterns

**TTS engines**: ABC with abstract `name`, `is_loaded`, `load()`, `synthesize()`, `list_voices()`. Concrete engines (`CoquiXTTSEngine`, `F5TTSEngine`, `PiperEngine`) implement `TTSEngine`. Engine swapped by config at startup.

**Tool system**: Abstract `Tool` base class with `to_openai_function()` concrete method. Tools dynamically generated from OpenAPI specs at startup via `discover_tools()`; stored in global `TOOLS` list.

**Intent routing**: Declarative `INTENT_EXAMPLES` dict maps intent labels to `(tool_filter, example_phrases)`. Add new domains by adding entries — no code changes elsewhere.

**Image generation providers**: `ImageGenProvider` ABC (`apps/dolores-imagen/src/dolores_imagen/engine.py`) defines abstract properties `name`, `is_loaded` and abstract methods `load()`, `generate(prompt, width, height) -> bytes`. Concrete providers (`FLUXProvider`, `StableDiffusionProvider`) implement the ABC; active provider selected via `IMAGEN_PROVIDER` env var at startup. `asyncio.to_thread()` + `asyncio.Semaphore(1)` in the route layer handle GPU offload and concurrency serialization — same pattern as TTS and STT services. Add a new provider by implementing the ABC; no route or config changes needed beyond adding the class and registering it in `main.py`.
