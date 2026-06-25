"""Async polling loop — periodically checks GitHub for open PRs and dispatches reviews."""

from __future__ import annotations

import asyncio
import time

from dolores_common.logging import get_logger

from .config import get_registry, get_settings, resolve_effective_config
from .github_client import list_open_prs, list_pr_comments
from .review_runner import run_review
from .state_store import get_state_store

log = get_logger(__name__)


async def run_polling_loop() -> None:
    """Outer polling loop — runs for the lifetime of the application.

    Iterates over all registered repositories once per poll cycle, catching
    per-repo exceptions so a single failing repo cannot block others.
    Sleeps for ``poll_interval_seconds`` between full cycles.
    """
    config = get_settings()
    registry = get_registry()
    store = get_state_store()

    while True:
        cycle_start = time.monotonic()
        log.info("poll_cycle_start")

        for repo_entry in registry.repositories:
            repo_name = getattr(repo_entry, "repo", str(repo_entry))
            try:
                await _poll_repo(repo_entry, store, config)
            except Exception:
                log.exception("poll_repo_error", repo=repo_name)

        elapsed = round(time.monotonic() - cycle_start, 3)
        log.info("poll_cycle_complete", elapsed_seconds=elapsed)

        await asyncio.sleep(config.poll_interval_seconds)


def _is_trigger_comment(body: str | None) -> bool:
    if not body:
        return False
    body_lower = body.lower()
    return "/review" in body_lower or "/re-review" in body_lower or "@review-bot review" in body_lower


async def _poll_repo(repo_entry, store, config) -> None:
    """Check a single repository for new or updated open PRs and dispatch reviews.

    SHA comparison and comment trigger logic:
    - ``stored_sha is None``        → new PR    → full diff
    - ``stored_sha != pr.head_sha`` → updated   → incremental diff
    - ``stored_sha == pr.head_sha`` → check for trigger comment
      - New comment matching '/review' → retrigger full review
      - Otherwise → skip

    Raises:
        RegistryError: if ``repo_entry.repo`` is not in the registry (caught by caller).
        Any exception from the GitHub client or review pipeline (caught by caller).
    """
    repo_name_full = repo_entry.repo
    owner, repo_name = repo_name_full.split("/", 1)

    try:
        effective = resolve_effective_config(repo_name_full)
    except Exception:
        log.exception("config_resolution_failed", repo=repo_name_full)
        return

    try:
        open_prs = await list_open_prs(owner, repo_name, effective.github_token)
    except Exception:
        log.exception("github_list_prs_failed", repo=repo_name_full)
        return

    review_tasks = []
    for pr in open_prs:
        stored_sha = await store.get_sha(repo_name_full, pr.number)
        stored_comment_id = await store.get_last_comment_id(repo_name_full, pr.number)

        # Check for trigger comments
        comments = []
        try:
            comments = await list_pr_comments(owner, repo_name, pr.number, effective.github_token)
        except Exception:
            log.exception("github_list_comments_failed", repo=repo_name_full, pr_number=pr.number)

        trigger_comments = [c for c in comments if _is_trigger_comment(c.get("body"))]
        if trigger_comments:
            latest_trigger = trigger_comments[-1]
            trigger_comment_id = latest_trigger["id"]
        else:
            trigger_comment_id = None

        max_comment_id = max((c["id"] for c in comments), default=None)

        should_review = False
        diff_type = "full"
        before_sha = None
        target_comment_id_to_store = max_comment_id

        if stored_sha != pr.head_sha:
            should_review = True
            if stored_sha is None:
                diff_type = "full"
                before_sha = None
                log.info("pr_detected_new", repo=repo_name_full, pr_number=pr.number, head_sha=pr.head_sha)
            else:
                diff_type = "incremental"
                before_sha = stored_sha
                log.info(
                    "pr_detected_updated",
                    repo=repo_name_full,
                    pr_number=pr.number,
                    head_sha=pr.head_sha,
                    before_sha=stored_sha,
                )
        elif trigger_comment_id is not None:
            if stored_comment_id is None or trigger_comment_id > stored_comment_id:
                should_review = True
                diff_type = "full"
                before_sha = None
                log.info(
                    "pr_detected_comment_retrigger",
                    repo=repo_name_full,
                    pr_number=pr.number,
                    head_sha=pr.head_sha,
                    comment_id=trigger_comment_id,
                )
                target_comment_id_to_store = max(trigger_comment_id, max_comment_id or 0)

        if not should_review:
            log.debug("pr_skipped_unchanged", repo=repo_name_full, pr_number=pr.number, sha=pr.head_sha)
            continue

        review_tasks.append(
            run_review(
                repo=repo_name_full,
                pr_number=pr.number,
                head_sha=pr.head_sha,
                diff_type=diff_type,
                before_sha=before_sha,
                last_comment_id=target_comment_id_to_store,
            )
        )

    if review_tasks:
        results = await asyncio.gather(*review_tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                # Individual PR review failed; log it but don't crash the repo poll
                log.error(
                    "pr_review_failed",
                    repo=repo_name_full,
                    error=str(res),
                    exc_info=res,
                )

