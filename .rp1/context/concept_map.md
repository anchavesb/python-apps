# Domain Concepts & Terminology

**Project**: python-apps (Dolores Monorepo)
**Domain**: Voice-First AI Assistant / Personal Productivity

## Core Concepts

### Dolores Assistant
**Definition**: Central orchestrator service that receives user voice or text input, routes it through the STT → Brain → TTS pipeline, manages the agent tool loop, and exposes a WebSocket conversation endpoint to clients.
**Implementation**: `apps/dolores-assistant/src/dolores_assistant/pipeline.py`, `routes.py`
**Key Properties**:
- WebSocket gateway for all client types (CLI, Web, Mobile)
- Intent-based tool routing with ONNX embedding classifier
- Sentence-level TTS streaming for low-latency audio

### Dolores Brain
**Definition**: LLM inference service backed by LiteLLM; routes chat requests to configured providers (Ollama, Anthropic, OpenAI), maintains conversation history in SQLite, and returns structured responses with optional tool_calls.
**Implementation**: `apps/dolores-brain/src/dolores_brain/conversation.py`, `routes.py`, `provider_config.py`

### Dolores STT
**Definition**: Speech-to-text service that transcribes audio files or streaming audio, and performs speaker identification against enrolled voice embeddings stored in SQLite.
**Implementation**: `apps/dolores-stt/src/dolores_stt/routes.py`, `speaker_store.py`

### Dolores TTS
**Definition**: Text-to-speech service with a pluggable engine interface (Coqui XTTS, F5 TTS, Piper); synthesizes text to 16-bit PCM WAV bytes; supports named voice profiles backed by reference audio files and SQLite metadata.
**Implementation**: `apps/dolores-tts/src/dolores_tts/engine.py`, `voice_profiles.py`, `routes.py`

### Dolores Web
**Definition**: Svelte SPA frontend that connects to the assistant over WebSocket, records mic audio, plays streamed TTS audio, renders an emotion-driven animated avatar, and manages OIDC authentication.
**Implementation**: `apps/dolores-web/src/lib/DoloresClient.ts`, `stores.svelte.ts`

### Todo App
**Definition**: Flask REST API exposing Todos, Notes, and WorkItems; supports both single-user JSON-file storage and multi-user PostgreSQL storage; consumed by the assistant as an auto-discovered tool integration via OpenAPI spec.
**Implementation**: `apps/todo/src/todo_app/api.py`, `storage.py`, `db_store.py`, `openapi_spec.py`

---

## Key Entities

| Entity | Service | Description |
|--------|---------|-------------|
| **Conversation** | Brain | Persistent chat session (UUID) with ordered messages in SQLite; resumable across connections |
| **VoiceProfile** | TTS | Named TTS persona with reference audio on disk and metadata (engine, ref_text) in SQLite |
| **SpeakerProfile** | STT | Enrolled speaker identity stored as float32 embedding (Resemblyzer) in SQLite; updated via running average |
| **Tool** | Assistant | Abstract base for LLM-callable functions; exposes name, description, JSON Schema params, async execute() |
| **OpenAPITool** | Assistant | Dynamically generated Tool from an OpenAPI operation; forwards user JWT at execution time |
| **Tool Registry** | Assistant | Module-level TOOLS list populated at startup; provides name-filter lookup for intent-based routing |
| **Intent Classifier** | Assistant | ONNX-based embedding classifier (all-MiniLM-L6-v2); maps messages to tool domains with confidence gating |
| **ServiceClient** | Assistant | HTTP client facade wrapping all downstream service calls; enforces GPU concurrency semaphores |
| **Avatar** | Web | Animated visual with 4 phases (idle, listening, thinking, speaking) and 6 emotions; driven by pipeline state + LLM emotion tags |
| **LLM Provider** | Brain | Abstraction over Ollama/Anthropic/OpenAI; configured via env vars, resolved through LiteLLM |
| **Todo / Note / WorkItem** | Todo | Domain entities: task items, free-form notes, and work log entries |

---

## Terminology Glossary

### Business Terms
- **STT**: Speech-to-Text — the `dolores-stt` microservice that transcribes audio input to text
- **TTS**: Text-to-Speech — the `dolores-tts` microservice that synthesizes text responses to WAV audio
- **Brain**: The `dolores-brain` LLM inference microservice; receives chat messages and returns completions or tool_calls via LiteLLM
- **Pipeline**: The STT → Brain → TTS processing chain orchestrated by the assistant; includes graceful degradation when services are unavailable
- **Tool Loop**: Iterative agent execution — send message → detect tool_calls → execute tools → send results back → repeat until text response (max 5 iterations)
- **Session**: A single WebSocket connection lifecycle between client and assistant; initialized with `session.start` carrying voice_id, provider, mode, and optional user_token

### Technical Terms
- **OpenAPI Discovery**: Startup process where the assistant fetches OpenAPI specs from configured integration URLs and auto-generates Tool instances
- **Intent Classification**: Embedding cosine-similarity classification of user messages against pre-computed intent centroids; selects tool_filter subset before the tool loop
- **PSK**: Pre-Shared Key — static bearer token for inter-service auth (`DOLORES_SERVICE_PSK` env var); skipped in dev mode when unset
- **OIDC**: OpenID Connect — user authentication in the web UI; access tokens forwarded as `user_token` through WebSocket to downstream tools
- **JWT Passthrough**: OIDC access token flows from web client → WebSocket session → `OpenAPITool.execute()` → Bearer on downstream HTTP calls; enables per-user data isolation
- **Sentence-Level TTS Streaming**: Splits Brain response text at sentence boundaries and synthesizes progressively so audio playback begins before full response is complete
- **GPU Concurrency Semaphore**: `asyncio.Semaphore(1)` per GPU-bound service (STT, TTS) to serialize requests and prevent OOM
- **AvatarPhase**: One of four animation states: idle, listening, thinking, speaking; derived from recording/thinking/audioPlaying flags
- **AvatarEmotion**: One of six expressive states: neutral, curious, happy, sad, surprised, empathetic; set by LLM emotion tags or keyword-based fallback
- **SSE**: Server-Sent Events — used for streaming Brain chat responses token-by-token to the assistant
- **WAL**: Write-Ahead Log — append-only log in JsonStore (todo app) for crash recovery; replayed with rotating backup fallback
- **Speaker Embedding**: Float32 vector representation of a speaker's voice (Resemblyzer); updated with running average on new samples
- **Reference Audio**: WAV file uploaded when creating a VoiceProfile; conditions voice cloning engines (Coqui XTTS, F5 TTS)
- **LiteLLM**: Third-party library used by dolores-brain to abstract over multiple LLM providers with prefixed model strings (e.g. `ollama/llama3.2`)
- **CONFIDENCE_THRESHOLD**: Minimum cosine similarity score (0.45) for intent classification; messages below bypass tool routing
- **Conversation ID**: UUID identifying a conversation session; persisted in localStorage; enables context continuity across WebSocket reconnects
- **dolores-common**: Shared library providing Pydantic models, auth middleware, error schemas, CORS/request-ID middleware, and logging utilities for all Dolores microservices

---

## Key Patterns

| Pattern | Context | Summary |
|---------|---------|---------|
| STT → Brain → TTS Pipeline | Voice conversation | Audio transcribed → LLM inference (optional tool loop) → speech synthesis → WAV streamed back |
| Agent Tool Loop | LLM function-calling | Iterate up to 5 times: send message → tool_calls → execute → send results → get text response |
| OpenAPI Auto-Discovery | Tool integration | Fetch OpenAPI specs at startup; auto-generate Tool instances; names prefixed by integration name |
| Embedding-Based Intent Routing | Tool selection | ONNX cosine similarity against intent centroids selects tool_filter; below threshold bypasses tools |
| JWT Passthrough for Multi-Tenancy | User data isolation | OIDC token flows from web UI through WS session into tool execute(), enabling per-user isolation |
| Graceful Degradation | Service availability | ServiceClient returns None on HTTP failures; pipeline continues in text-only or audio-only mode |
| Pluggable TTS Engine | Hardware flexibility | TTSEngine ABC with synthesize/load/list_voices; XTTS/F5-TTS/Piper swappable at startup |

---

## Bounded Contexts

| Context | Scope | Owns |
|---------|-------|------|
| Voice Processing | dolores-stt, dolores-tts | Audio I/O: transcription, speaker ID, speech synthesis |
| LLM Inference | dolores-brain | LLM calls, conversation history; no audio or tool execution |
| Conversation Orchestration | dolores-assistant | End-to-end flow: STT, Brain, TTS, tool loop, WebSocket API |
| Integration Services | apps/todo | Domain services consumed via OpenAPI; own storage and per-user isolation |
| Web Frontend | dolores-web | Browser UI, audio capture/playback, OIDC token management |
| Shared Infrastructure | libs/dolores-common | Cross-cutting: auth primitives, models, error schemas, CORS/request-ID middleware |

---

## Cross-Cutting Concerns

| Concern | Approach |
|---------|----------|
| Authentication | Dual-layer: PSK for inter-service, API key for clients, OIDC JWT passthrough for user data; dev-mode bypass when env vars unset |
| Error Handling | Standard ErrorResponse JSON; pipeline degrades gracefully on None; tool loop catches exceptions and returns error strings to LLM |
| Structured Logging | structlog across all services; request_id bound per request via middleware; snake_case key=value log events |
| Request ID Tracing | `add_common_middleware` generates or propagates `x-request-id`; bound to structlog context for log correlation |
| Async Persistence | aiosqlite for Brain (conversations) and TTS (voice_profiles); synchronous sqlite3 + asyncio.to_thread for STT (speaker_store) |
| Session Expiry | JWT expiry detected client-side (isTokenExpired) and server-side in tool loop; triggers OIDC silent refresh or re-login prompt |

---

## Cross-References
- **System Architecture**: See `architecture.md`
- **Module Breakdown**: See `modules.md`
- **Implementation Patterns**: See `patterns.md`
