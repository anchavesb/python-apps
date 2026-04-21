# Dolores — VAD + Streaming STT + Long-term Memory

## Context
3 sequential features on 3 separate branches. Each branch: implement → tests → lint → e2e → PR → approval → merge.
No wake word. Tab open = intent boundary. Push-to-talk stays as fallback.
STT/TTS toggles preserved. Memory gets a full management UI.

---

## Git Strategy
```
main
 └─ feature/vad                 (frontend-only, no server changes)
 └─ feature/streaming-stt       (server + frontend, depends on VAD UX)
 └─ feature/long-term-memory    (server + frontend, independent)
```
Each branch from main. PR created before any merge. Approval required before next feature starts.

---

## Feature 1: VAD — Branch `feature/vad`

### Scope
Frontend only. No server changes. Adds auto-listen mode alongside existing push-to-talk.

### Dependencies
```
npm install @ricky0123/vad-web
```

### Files to modify

#### `apps/dolores-web/src/lib/AudioRecorder.ts`
Add `VADAudioRecorder` class alongside existing `AudioRecorder` (keep both):

```typescript
import { MicVAD, utils } from '@ricky0123/vad-web'

export class VADAudioRecorder {
  private vad: MicVAD | null = null

  async init(callbacks: {
    onSpeechStart: () => void
    onSpeechEnd: (audio: Float32Array) => void
  }): Promise<void> {
    this.vad = await MicVAD.new({
      positiveSpeechThreshold: 0.85,
      negativeSpeechThreshold: 0.50,
      minSpeechFrames: 5,        // ~150ms minimum utterance
      preSpeechPadFrames: 10,    // 300ms pre-buffer (capture word start)
      redemptionFrames: 8,       // 240ms silence before onSpeechEnd fires
      ...callbacks,
    })
  }

  start(): void { this.vad?.start() }
  pause(): void { this.vad?.pause() }
  destroy(): void { this.vad?.destroy(); this.vad = null }

  // Encode Float32Array (16kHz mono PCM) → WAV Blob
  static encodeWav(float32: Float32Array, sampleRate = 16000): Blob {
    return new Blob([utils.encodeWAV(float32, sampleRate)], { type: 'audio/wav' })
  }
}
```

#### `apps/dolores-web/src/lib/stores.svelte.ts`
- Add `vadMode: boolean` to `AppState` (persisted in localStorage)
- Add `VADAudioRecorder` instance alongside existing `AudioRecorder`
- Echo prevention: pause VAD when `audioPlaying === true`
- Visibility prevention: pause VAD when tab backgrounded (Page Visibility API)
- STT/TTS toggles unchanged — VAD is independent input method

```typescript
// New state field
interface AppState {
  // ... existing fields ...
  vadMode: boolean   // false = push-to-talk (default), true = auto-listen
}

// VAD init (called on connect when vadMode=true)
async function initVAD(): Promise<void> {
  await vadRecorder.init({
    onSpeechStart: () => {
      if (state.audioPlaying) return    // Dolores speaking → ignore
      player.stop()
      state.recording = true
      client.sendAudioStart()
    },
    onSpeechEnd: async (audio: Float32Array) => {
      if (!state.recording) return
      state.recording = false
      const blob = VADAudioRecorder.encodeWav(audio)
      const buffer = await blob.arrayBuffer()
      if (buffer.byteLength < 1000) return  // too short, ignore
      state.thinking = true
      state.streamingText = ''
      state.emotion = 'neutral'
      client.sendAudioChunk(buffer)
      client.sendAudioEnd('audio/wav')
    },
  })
  vadRecorder.start()
}

// Echo prevention (reactive)
$effect(() => {
  if (state.vadMode && state.connected) {
    if (state.audioPlaying || state.recording) vadRecorder.pause()
    else vadRecorder.start()
  }
})

// Tab visibility
document.addEventListener('visibilitychange', () => {
  if (!state.vadMode || !state.connected) return
  document.hidden ? vadRecorder.pause() : vadRecorder.start()
})
```

#### `apps/dolores-web/src/routes/+page.svelte` (or settings component)
Add "Auto-listen" toggle in settings panel:
```svelte
<label>
  <input type="checkbox" bind:checked={app.state.vadMode}
         on:change={() => app.saveSettings()} />
  Auto-listen (VAD)
</label>
```
Push-to-talk button remains, but hidden when `vadMode=true` (or kept as manual override).

### Tests
No server-side tests needed. VAD is third-party WASM — trust the library.
Add a Vitest unit test for `VADAudioRecorder.encodeWav()`:

#### `apps/dolores-web/src/lib/AudioRecorder.test.ts` (new)
```typescript
import { describe, it, expect } from 'vitest'
import { VADAudioRecorder } from './AudioRecorder'

describe('VADAudioRecorder.encodeWav', () => {
  it('produces a WAV blob with correct MIME type', () => {
    const silence = new Float32Array(1600)  // 100ms @ 16kHz
    const blob = VADAudioRecorder.encodeWav(silence)
    expect(blob.type).toBe('audio/wav')
    expect(blob.size).toBeGreaterThan(44)   // at minimum the WAV header
  })

  it('handles empty audio gracefully', () => {
    const empty = new Float32Array(0)
    const blob = VADAudioRecorder.encodeWav(empty)
    expect(blob.size).toBeGreaterThanOrEqual(44)  // header only
  })
})
```

### Linter + E2E
```bash
cd apps/dolores-web && npm run check   # svelte-check + tsc
cd apps/dolores-web && npx vitest run  # unit tests
make lint                              # ruff (no Python changes, still good hygiene)
make test-e2e                          # existing E2E suite
```

### PR checklist
- [ ] `vadMode` persisted in localStorage, default `false`
- [ ] Push-to-talk still works when `vadMode=false`
- [ ] TTS toggle (`ttsEnabled`) unchanged
- [ ] STT mode (`text` vs `both`) unchanged
- [ ] VAD pauses when Dolores is speaking
- [ ] VAD pauses when tab backgrounded
- [ ] WAV encoder unit tests pass
- [ ] `npm run check` clean
- [ ] e2e pass

---

## Feature 2: Streaming STT — Branch `feature/streaming-stt`

### Scope
Show partial transcription text in UI as Whisper decodes.
Pipes existing (unused) STT `/v1/stream` WebSocket through the assistant.

### Key insight from code audit
- `dolores-stt/engine.py:157` — `transcribe_stream()` already yields partial segments ✓
- `dolores-stt/routes.py:196` — `/v1/stream` WS already exists ✓
- `dolores-assistant/pipeline.py:145` — `transcribe()` ignores both, does batch POST ✗

### Dependencies
Add to `apps/dolores-assistant/pyproject.toml`:
```toml
websockets>=12.0
```

### Files to modify

#### `apps/dolores-assistant/src/dolores_assistant/pipeline.py`
Add `transcribe_streaming()` to `ServiceClient`:

```python
async def transcribe_streaming(
    self,
    audio_data: bytes,
    content_type: str = "audio/webm",
    language: str | None = None,
):
    """Async generator: yields partial/final transcription chunks via STT WS.

    Falls back to batch transcribe() on WS failure so no regression.
    Yields: {"type": "partial"|"final", "text": str, "language": str}
    """
    import websockets

    stt_ws_url = settings.stt_url.replace("http://", "ws://").replace("https://", "wss://")
    psk = os.environ.get("DOLORES_SERVICE_PSK", "")
    extra_headers = {"Authorization": f"Bearer {psk}"} if psk else {}

    try:
        async with _stt_semaphore:
            async with websockets.connect(
                f"{stt_ws_url}/v1/stream",
                additional_headers=extra_headers,
                open_timeout=5,
            ) as ws:
                await ws.send(audio_data)
                await ws.send(json.dumps({"type": "audio.end", "language": language}))

                async for raw in ws:
                    chunk = json.loads(raw)
                    yield chunk
                    if chunk.get("type") == "final":
                        break
    except Exception as e:
        log.warning("stt_stream_fallback_to_batch", error=str(e))
        result = await self.transcribe(audio_data, content_type, language)
        if result:
            yield {"type": "final", "text": result["text"], "language": result.get("language", "")}
```

Note: `_stt_semaphore` reused — prevents GPU contention same as batch path.

#### `apps/dolores-assistant/src/dolores_assistant/routes.py`
In `conversation_ws`, `audio.end` handler — replace batch transcribe with streaming:

```python
# OLD:
transcription, speaker_result = await asyncio.gather(
    client.transcribe(audio_data, content_type=content_type),
    client.identify_speaker(audio_data, content_type=content_type),
    return_exceptions=True,
)

# NEW:
# Speaker ID fires immediately, in parallel with streaming STT
speaker_task = asyncio.create_task(
    client.identify_speaker(audio_data, content_type=content_type)
)

final_text = ""
detected_language = ""
async for chunk in client.transcribe_streaming(audio_data, content_type):
    if chunk["type"] == "partial" and chunk.get("text"):
        await websocket.send_json({
            "type": "transcription.partial",
            "text": chunk["text"],
        })
    elif chunk["type"] == "final":
        final_text = chunk["text"]
        detected_language = chunk.get("language", "")

speaker_result = await speaker_task
if isinstance(speaker_result, Exception):
    speaker_result = None

transcription = {"text": final_text, "language": detected_language} if final_text else None
# rest of handler unchanged from line 358 onward
```

#### `apps/dolores-web/src/lib/stores.svelte.ts`
Handle `transcription.partial` event — show live captions:
```typescript
case 'transcription.partial':
  state.transcription = msg.text  // already displayed in UI
  break
```
`transcription` field already in `AppState` (line 35). No new fields needed.

### Tests

#### `apps/dolores-assistant/tests/test_streaming_stt.py` (new)
```python
"""Tests for ServiceClient.transcribe_streaming() with fallback behavior."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from dolores_assistant.pipeline import ServiceClient


class TestTranscribeStreaming:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = ServiceClient()
        self.client._client = AsyncMock()

    @pytest.mark.asyncio
    async def test_fallback_on_ws_failure(self):
        """When WebSocket fails, falls back to batch transcribe, yields final chunk."""
        self.client._client.post = AsyncMock(return_value=_make_transcription_response("hello world"))

        with patch("websockets.connect", side_effect=OSError("refused")):
            chunks = []
            async for chunk in self.client.transcribe_streaming(b"audio", "audio/wav"):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "final"
        assert chunks[0]["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_partial_then_final_from_ws(self):
        """WS yields partial segments then final — all forwarded."""
        messages = [
            json.dumps({"type": "partial", "text": "hello", "language": "en"}),
            json.dumps({"type": "partial", "text": "hello world", "language": "en"}),
            json.dumps({"type": "final", "text": "hello world", "language": "en"}),
        ]
        fake_ws = _make_ws_mock(messages)

        with patch("websockets.connect") as mock_connect:
            mock_connect.return_value.__aenter__ = AsyncMock(return_value=fake_ws)
            mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)
            chunks = []
            async for chunk in self.client.transcribe_streaming(b"audio"):
                chunks.append(chunk)

        types = [c["type"] for c in chunks]
        assert types == ["partial", "partial", "final"]
        assert chunks[-1]["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_empty_fallback_result(self):
        """Batch fallback returns None → no chunks yielded."""
        self.client.transcribe = AsyncMock(return_value=None)

        with patch("websockets.connect", side_effect=OSError("refused")):
            chunks = []
            async for chunk in self.client.transcribe_streaming(b"audio"):
                chunks.append(chunk)

        assert chunks == []


def _make_transcription_response(text: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"text": text, "language": "en", "segments": [],
                               "language_probability": 0.99, "duration_seconds": 1.0,
                               "processing_time_ms": 100}
    return resp


def _make_ws_mock(messages: list[str]):
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.__aiter__ = lambda self: iter(messages)
    return ws
```

### Linter + E2E
```bash
make lint          # ruff check
make test          # unit tests (includes new test_streaming_stt.py)
make test-e2e      # e2e suite
```

### PR checklist
- [ ] `transcribe_streaming()` added to `ServiceClient`
- [ ] WS failure → batch fallback, no error surfaced to user
- [ ] `transcription.partial` events sent to frontend
- [ ] Speaker ID still runs in parallel (no regression)
- [ ] `_stt_semaphore` still respected
- [ ] Existing batch `transcribe()` method unchanged (used in fallback + REST endpoint)
- [ ] Unit tests pass (including fallback + partial+final scenarios)
- [ ] `make lint` clean
- [ ] e2e pass

---

## Feature 3: Long-term Memory — Branch `feature/long-term-memory`

### Scope
- `dolores-assistant`: MemoryStore, extraction, injection, API endpoints
- `dolores-web`: Memory management panel (view, edit, delete memories)
- Reuses `all-MiniLM-L6-v2` ONNX model already in `intent.py`
- No new vector DB — SQLite + numpy cosine similarity

### Files to add

#### `apps/dolores-assistant/src/dolores_assistant/memory.py` (new)
Full implementation:

```python
"""Long-term episodic memory: fact storage, embedding, cosine retrieval."""
from __future__ import annotations
import struct, uuid
from datetime import datetime, timezone

import aiosqlite
import numpy as np
from dolores_common.logging import get_logger

log = get_logger(__name__)

_CREATE = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    fact TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
"""

class MemoryStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        for stmt in _CREATE.strip().split(";"):
            if stmt.strip():
                await self._db.execute(stmt)
        await self._db.commit()

    async def close(self) -> None:
        if self._db: await self._db.close()

    def _pack(self, emb: list[float]) -> bytes:
        return struct.pack(f"{len(emb)}f", *emb)

    def _unpack(self, blob: bytes) -> np.ndarray:
        n = len(blob) // 4
        return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)

    async def save(self, user_id: str, fact: str, embedding: list[float]) -> str:
        mid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO memories (id, user_id, fact, embedding, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (mid, user_id, fact, self._pack(embedding), now, now),
        )
        await self._db.commit()
        return mid

    async def search(self, user_id: str, query_emb: list[float], top_k: int = 5) -> list[str]:
        cur = await self._db.execute(
            "SELECT fact, embedding FROM memories WHERE user_id = ?", (user_id,)
        )
        rows = await cur.fetchall()
        if not rows: return []
        q = np.array(query_emb, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        scored = []
        for fact, blob in rows:
            emb = self._unpack(blob)
            emb /= np.linalg.norm(emb) + 1e-9
            scored.append((float(np.dot(q, emb)), fact))
        scored.sort(reverse=True)
        return [f for score, f in scored[:top_k] if score > 0.4]

    async def list_all(self, user_id: str) -> list[dict]:
        cur = await self._db.execute(
            "SELECT id, fact, created_at, updated_at FROM memories WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cur.fetchall()
        return [{"id": r[0], "fact": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    async def update(self, memory_id: str, user_id: str, fact: str, embedding: list[float]) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cur = await self._db.execute(
            "UPDATE memories SET fact=?, embedding=?, updated_at=? WHERE id=? AND user_id=?",
            (fact, self._pack(embedding), now, memory_id, user_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def delete(self, memory_id: str, user_id: str) -> bool:
        cur = await self._db.execute(
            "DELETE FROM memories WHERE id=? AND user_id=?", (memory_id, user_id)
        )
        await self._db.commit()
        return cur.rowcount > 0
```

#### `apps/dolores-assistant/src/dolores_assistant/tools/memory_tools.py` (new)
```python
from .base import Tool
from ..memory import MemoryStore

class MemoryRememberTool(Tool):
    name = "memory_remember"
    description = "Save a specific fact about the user to long-term memory"
    parameters = {
        "type": "object",
        "properties": {"fact": {"type": "string", "description": "The fact to remember"}},
        "required": ["fact"],
    }
    def __init__(self, store: MemoryStore, user_id: str): ...
    async def execute(self, *, fact: str) -> str: ...

class MemoryRecallTool(Tool):
    name = "memory_recall"
    description = "Search long-term memory for facts about the user"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    async def execute(self, *, query: str) -> str: ...

class MemoryForgetTool(Tool):
    name = "memory_forget"
    description = "Delete a specific fact from long-term memory"
    parameters = {
        "type": "object",
        "properties": {"fact_substring": {"type": "string"}},
        "required": ["fact_substring"],
    }
    async def execute(self, *, fact_substring: str) -> str: ...
```

Register all 3 in `apps/dolores-assistant/src/dolores_assistant/tools/registry.py`.

### Files to modify

#### `apps/dolores-assistant/src/dolores_assistant/config.py`
```python
memory_db_path: str = Field(default="data/memory.db", env="MEMORY_DB_PATH")
```

#### `apps/dolores-assistant/src/dolores_assistant/intent.py`
Expose `get_embedding()` as a public function (extract from internal classify_intent logic):
```python
def get_embedding(text: str) -> list[float]:
    """Return all-MiniLM-L6-v2 embedding vector for text. 384-dim float list."""
    # Same tokenizer + ONNX session already used in classify_intent()
    ...
```

#### `apps/dolores-assistant/src/dolores_assistant/main.py`
Init `MemoryStore` in lifespan, expose via `app.state.memory`:
```python
from .memory import MemoryStore
# In lifespan:
memory = MemoryStore(settings.memory_db_path)
await memory.init()
app.state.memory = memory
# ... existing
yield
await memory.close()
```

#### `apps/dolores-assistant/src/dolores_assistant/pipeline.py`
1. **Memory injection in `run_tool_loop()`** — add `memory_store` + `user_id` params:
```python
async def run_tool_loop(
    ...,
    memory_store=None,
    user_id: str = "anonymous",
) -> dict:
    memory_context = ""
    if memory_store:
        try:
            from .intent import get_embedding
            emb = get_embedding(initial_message)
            facts = await memory_store.search(user_id, emb, top_k=5)
            if facts:
                memory_context = "\n\nREMEMBERED FACTS ABOUT THIS USER:\n" + "\n".join(f"- {f}" for f in facts)
        except Exception as e:
            log.warning("memory_retrieval_failed", error=str(e))
    # Append to system prompt
    system = get_system_prompt(model) + memory_context
    # pass system to client.chat() calls
```

2. **Add `extract_and_save_memories()` helper**:
```python
async def extract_and_save_memories(
    client: ServiceClient,
    session_messages: list[dict],   # list of {role, content} from the session
    memory_store,
    user_id: str,
    provider: str,
    model: str | None,
) -> None:
    """Fire-and-forget: LLM extracts facts from session, saves to memory."""
    if len(session_messages) < 4:
        return   # skip trivial sessions

    history = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in session_messages[-20:]
        if isinstance(m.get("content"), str)
    )
    prompt = (
        "Extract factual statements the user revealed about themselves in this conversation. "
        "Output ONLY lines starting with 'FACT:'. One fact per line. "
        "Examples:\n  FACT: user's name is Andrea.\n  FACT: user works in software.\n"
        "  FACT: user prefers concise answers.\n"
        "If no personal facts were shared, output nothing.\n\n"
        f"CONVERSATION:\n{history}"
    )
    result = await client.chat(
        message=prompt,
        provider=provider,
        model=model,
        system_prompt="Extract facts only. Output FACT: lines or nothing.",
    )
    if not result:
        return
    from .intent import get_embedding
    for line in result.get("message", "").splitlines():
        if line.startswith("FACT:"):
            fact = line[5:].strip()
            if fact:
                emb = get_embedding(fact)
                await memory_store.save(user_id, fact, emb)
                log.info("memory_saved", user_id=user_id, fact=fact[:80])
```

#### `apps/dolores-assistant/src/dolores_assistant/routes.py`
1. **Extract user_id from JWT** (new helper):
```python
def _get_user_id(token: str | None) -> str:
    if not token:
        return "anonymous"
    try:
        import base64, json
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("sub") or data.get("email") or "anonymous"
    except Exception:
        return "anonymous"
```

2. **In `conversation_ws`**:
   - Track `session_messages: list[dict] = []`, append user + assistant turns
   - Pass `memory_store=request.app.state.memory`, `user_id=session_user_id` to `run_tool_loop()`
   - On disconnect: `asyncio.create_task(extract_and_save_memories(...))`

3. **Memory management API endpoints** (new routes in `routes.py`):
```python
@router.get("/memories")
async def list_memories(request: Request, _auth: ClientAPIKey = None) -> list[dict]:
    """List all memories for the current user."""
    token = request.headers.get("x-user-token")
    user_id = _get_user_id(token)
    return await request.app.state.memory.list_all(user_id)

@router.patch("/memories/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdateRequest, request: Request, _auth: ClientAPIKey = None):
    """Edit a memory's text."""
    token = request.headers.get("x-user-token")
    user_id = _get_user_id(token)
    from .intent import get_embedding
    emb = get_embedding(body.fact)
    updated = await request.app.state.memory.update(memory_id, user_id, body.fact, emb)
    if not updated:
        raise HTTPException(404, "Memory not found")
    return {"id": memory_id, "fact": body.fact}

@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, request: Request, _auth: ClientAPIKey = None):
    """Delete a memory by ID."""
    token = request.headers.get("x-user-token")
    user_id = _get_user_id(token)
    deleted = await request.app.state.memory.delete(memory_id, user_id)
    if not deleted:
        raise HTTPException(404, "Memory not found")
    return Response(status_code=204)
```

Add `MemoryUpdateRequest` Pydantic model to `schemas.py`:
```python
class MemoryUpdateRequest(BaseModel):
    fact: str
```

### Memory Management UI

#### `apps/dolores-web/src/lib/MemoryPanel.svelte` (new component)
Panel accessible from settings or sidebar:
- List all memories (GET /v1/memories)
- Inline edit: click fact → text input → save (PATCH /v1/memories/{id})
- Delete button per memory (DELETE /v1/memories/{id})
- "Clear all" option
- Shows `created_at` timestamp
- Empty state: "No memories yet — chat to build them up"

```svelte
<script lang="ts">
  let memories = $state<Memory[]>([])
  let editing = $state<string | null>(null)  // memory id being edited
  let editText = $state('')

  onMount(async () => { memories = await fetchMemories() })

  async function save(id: string) {
    await updateMemory(id, editText)
    memories = memories.map(m => m.id === id ? {...m, fact: editText} : m)
    editing = null
  }

  async function remove(id: string) {
    await deleteMemory(id)
    memories = memories.filter(m => m.id !== id)
  }
</script>

<div class="memory-panel">
  <h3>Memories ({memories.length})</h3>
  {#each memories as mem}
    <div class="memory-item">
      {#if editing === mem.id}
        <input bind:value={editText} />
        <button onclick={() => save(mem.id)}>Save</button>
        <button onclick={() => editing = null}>Cancel</button>
      {:else}
        <span>{mem.fact}</span>
        <button onclick={() => { editing = mem.id; editText = mem.fact }}>Edit</button>
        <button onclick={() => remove(mem.id)}>Delete</button>
      {/if}
    </div>
  {/each}
  {#if memories.length === 0}
    <p>No memories yet — chat to build them up.</p>
  {/if}
</div>
```

Add to settings modal or as a tab in the existing settings panel.

### Tests

#### `apps/dolores-assistant/tests/test_memory.py` (new)
```python
"""Unit tests for MemoryStore: save, search, list, update, delete."""
import asyncio
import pytest
from dolores_assistant.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "test_memory.db"))
    asyncio.run(s.init())
    yield s
    asyncio.run(s.close())


class TestMemoryStore:
    def test_save_and_list(self, store):
        emb = [0.1] * 384
        asyncio.run(store.save("user1", "user likes coffee", emb))
        memories = asyncio.run(store.list_all("user1"))
        assert len(memories) == 1
        assert memories[0]["fact"] == "user likes coffee"

    def test_search_returns_similar(self, store):
        # Save a fact with a known embedding
        emb = [1.0] + [0.0] * 383  # unit vector in dim 0
        asyncio.run(store.save("user1", "user's name is Andrea", emb))

        # Query with same embedding → should retrieve
        results = asyncio.run(store.search("user1", emb, top_k=5))
        assert "user's name is Andrea" in results

    def test_search_below_threshold_excluded(self, store):
        # Save with embedding pointing in opposite direction
        emb_save = [1.0] + [0.0] * 383
        emb_query = [-1.0] + [0.0] * 383  # cosine = -1, well below 0.4 threshold
        asyncio.run(store.save("user1", "some fact", emb_save))
        results = asyncio.run(store.search("user1", emb_query))
        assert results == []

    def test_user_isolation(self, store):
        emb = [0.1] * 384
        asyncio.run(store.save("user1", "user1 fact", emb))
        asyncio.run(store.save("user2", "user2 fact", emb))
        u1 = asyncio.run(store.list_all("user1"))
        u2 = asyncio.run(store.list_all("user2"))
        assert len(u1) == 1 and u1[0]["fact"] == "user1 fact"
        assert len(u2) == 1 and u2[0]["fact"] == "user2 fact"

    def test_update(self, store):
        emb = [0.1] * 384
        mid = asyncio.run(store.save("user1", "old fact", emb))
        updated = asyncio.run(store.update(mid, "user1", "new fact", emb))
        assert updated is True
        memories = asyncio.run(store.list_all("user1"))
        assert memories[0]["fact"] == "new fact"

    def test_update_wrong_user_fails(self, store):
        emb = [0.1] * 384
        mid = asyncio.run(store.save("user1", "private fact", emb))
        updated = asyncio.run(store.update(mid, "user2", "hacked", emb))
        assert updated is False

    def test_delete(self, store):
        emb = [0.1] * 384
        mid = asyncio.run(store.save("user1", "temp fact", emb))
        deleted = asyncio.run(store.delete(mid, "user1"))
        assert deleted is True
        assert asyncio.run(store.list_all("user1")) == []

    def test_delete_wrong_user_fails(self, store):
        emb = [0.1] * 384
        mid = asyncio.run(store.save("user1", "protected", emb))
        deleted = asyncio.run(store.delete(mid, "user2"))
        assert deleted is False
```

#### `apps/dolores-assistant/tests/test_memory_extraction.py` (new)
```python
"""Tests for extract_and_save_memories() pipeline helper."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from dolores_assistant.pipeline import extract_and_save_memories


class TestMemoryExtraction:
    def test_skips_short_sessions(self):
        """Sessions with fewer than 4 messages → no extraction."""
        store = AsyncMock()
        client = AsyncMock()
        asyncio.run(extract_and_save_memories(client, [{"role": "user", "content": "hi"}], store, "u1", "ollama", None))
        client.chat.assert_not_called()
        store.save.assert_not_called()

    def test_saves_extracted_facts(self):
        """FACT: lines from LLM response → saved to store."""
        store = AsyncMock()
        client = AsyncMock()
        client.chat.return_value = {"message": "FACT: user's name is Andrea.\nFACT: user likes Python."}

        messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
                    {"role": "user", "content": "i'm andrea"}, {"role": "assistant", "content": "nice"}]

        with patch("dolores_assistant.pipeline.get_embedding", return_value=[0.1] * 384):
            asyncio.run(extract_and_save_memories(client, messages, store, "u1", "ollama", None))

        assert store.save.call_count == 2

    def test_ignores_non_fact_lines(self):
        """Lines without FACT: prefix are ignored."""
        store = AsyncMock()
        client = AsyncMock()
        client.chat.return_value = {"message": "Here are some notes:\nFACT: user is a developer.\nSome other text."}
        messages = [{"role": msg, "content": "x"} for msg in ["user","assistant","user","assistant"]]

        with patch("dolores_assistant.pipeline.get_embedding", return_value=[0.1] * 384):
            asyncio.run(extract_and_save_memories(client, messages, store, "u1", "ollama", None))

        assert store.save.call_count == 1
```

#### `apps/dolores-assistant/tests/test_memory_routes.py` (new)
```python
"""Integration tests for /v1/memories API endpoints."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient


# Use FastAPI TestClient with mocked app.state.memory
# Tests: GET /v1/memories, PATCH /v1/memories/{id}, DELETE /v1/memories/{id}
# Following patterns from existing test_pipeline.py
```

### Linter + E2E
```bash
make lint          # ruff check
make test          # pytest (includes test_memory.py, test_memory_extraction.py)
make test-e2e      # e2e suite
cd apps/dolores-web && npm run check   # svelte-check
```

### PR checklist
- [ ] `MemoryStore` save/search/update/delete/list_all all tested
- [ ] User isolation enforced at DB level (user_id in all queries)
- [ ] Memory injection in `run_tool_loop()` (system prompt enriched)
- [ ] Memory extraction fires async on WS disconnect (fire-and-forget)
- [ ] `memory_remember`, `memory_recall`, `memory_forget` tools registered
- [ ] GET/PATCH/DELETE `/v1/memories` endpoints working
- [ ] `MemoryPanel.svelte` renders list, supports inline edit + delete
- [ ] STT/TTS toggles unaffected
- [ ] `make lint` clean
- [ ] `make test` all pass
- [ ] e2e pass

---

## Execution Order

```
1. feature/vad
   → implement → npm run check → vitest → make lint → make test-e2e
   → open PR → await approval → merge

2. feature/streaming-stt (branch from main after 1 merges)
   → implement → make lint → make test → make test-e2e
   → open PR → await approval → merge

3. feature/long-term-memory (branch from main after 2 merges)
   → implement → make lint → make test → make test-e2e
   → open PR → await approval → merge
```
