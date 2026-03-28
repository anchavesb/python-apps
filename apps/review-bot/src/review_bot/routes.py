"""HTTP routes for review-bot — GET /health and POST /v1/review."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from dolores_common.health import create_health_router

from .config import RegistryError, resolve_effective_config
from .github_client import get_github_client
from .review_runner import get_semaphore, run_review
from .schemas import ReviewAccepted, ReviewRequest, ReviewSkipped
from .state_store import get_state_store

router = APIRouter()
router.include_router(create_health_router("review-bot", "0.1.0"))


async def _require_review_bot_psk(request: Request) -> None:
    """Validate the REVIEW_BOT_PSK bearer token.

    Skips validation when REVIEW_BOT_PSK is not set (dev mode).
    Raises HTTP 401 for missing or invalid tokens.
    """
    psk = os.environ.get("REVIEW_BOT_PSK")
    if not psk:
        return

    authorization = request.headers.get("authorization", "")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != psk:
        raise HTTPException(status_code=401, detail="Invalid or missing PSK bearer token")


ReviewBotPSK = Annotated[None, Depends(_require_review_bot_psk)]


@router.post(
    "/v1/review",
    status_code=202,
    response_model=None,
    responses={200: {"model": ReviewSkipped}, 202: {"model": ReviewAccepted}},
)
async def trigger_review(
    body: ReviewRequest,
    background_tasks: BackgroundTasks,
    _: ReviewBotPSK,
) -> ReviewAccepted | Response:
    """Manual on-demand review trigger.

    Response codes:
    - 202 Accepted        — review queued as a background task
    - 200 OK              — PR already reviewed at current SHA and force=False
    - 401 Unauthorized    — missing or invalid PSK bearer token
    - 503 Unavailable     — concurrency semaphore exhausted; retry after 30s
    """
    owner, name = body.repo.split("/", 1)
    try:
        effective = resolve_effective_config(body.repo)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    github = get_github_client()
    store = get_state_store()
    sem = get_semaphore()

    pr_info = await github.get_pr_info(owner, name, body.pr_number, effective.github_token)
    stored_sha = await store.get_sha(body.repo, body.pr_number)

    if stored_sha == pr_info.head_sha and not body.force:
        skipped = ReviewSkipped(
            status="already_reviewed", repo=body.repo, pr_number=body.pr_number, sha=pr_info.head_sha
        )
        return JSONResponse(status_code=200, content=skipped.model_dump())

    if sem.locked():
        raise HTTPException(
            status_code=503,
            detail="Review concurrency limit reached. Retry after current reviews complete.",
            headers={"Retry-After": "30"},
        )

    background_tasks.add_task(
        run_review,
        repo=body.repo,
        pr_number=body.pr_number,
        head_sha=pr_info.head_sha,
        diff_type="full",
        before_sha=None,
    )
    return ReviewAccepted(status="accepted", repo=body.repo, pr_number=body.pr_number, head_sha=pr_info.head_sha)
