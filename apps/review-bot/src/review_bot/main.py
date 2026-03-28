"""FastAPI application for review-bot."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from dolores_common.logging import setup_logging
from dolores_common.middleware import add_common_middleware

from .config import load_registry, settings
from .github_client import set_github_client
from .poller import run_polling_loop
from .prompt import load_base_prompt
from .review_runner import init_semaphore
from .routes import router as review_router
from .state_store import StateStore, set_state_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("review-bot", settings.log_level, json_output=settings.log_format == "json")
    load_registry(settings.registry_path)
    load_base_prompt(settings.prompts_dir)
    client = httpx.AsyncClient(timeout=30.0)
    set_github_client(client)
    store = StateStore(settings.state_db_path)
    await store.init()
    set_state_store(store)
    init_semaphore(settings.max_concurrent_reviews)
    task = asyncio.create_task(run_polling_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await store.close()
    await client.aclose()


app = FastAPI(title="review-bot", lifespan=lifespan)

add_common_middleware(app)
app.include_router(review_router)
