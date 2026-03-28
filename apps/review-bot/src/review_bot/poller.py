"""Async polling loop — periodically checks GitHub for open PRs and dispatches reviews."""

from __future__ import annotations

import asyncio
import time

from dolores_common.logging import get_logger

from .config import get_registry, get_settings, resolve_effective_config
from .github_client import get_github_client
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
            try:
                await _poll_repo(repo_entry, store, config)
            except Exception:
                log.exception("poll_repo_error", repo=repo_entry.repo)

        elapsed = round(time.monotonic() - cycle_start, 3)
        log.info("poll_cycle_complete", elapsed_seconds=elapsed)

        await asyncio.sleep(config.poll_interval_seconds)


async def _poll_repo(repo_entry, store, config) -> None:
    """Check a single repository for new or updated open PRs and dispatch reviews.

    SHA comparison logic:
    - ``stored_sha is None``        → new PR    → full diff
    - ``stored_sha != pr.head_sha`` → updated   → incremental diff
    - ``stored_sha == pr.head_sha`` → unchanged → skip

    Raises:
        RegistryError: if ``repo_entry.repo`` is not in the registry (caught by caller).
        Any exception from the GitHub client or review pipeline (caught by caller).
    """
    github = get_github_client()
    owner, repo_name = repo_entry.repo.split("/", 1)
    effective = resolve_effective_config(repo_entry.repo)
    open_prs = await github.list_open_prs(owner, repo_name, effective.github_token)

    review_tasks = []
    for pr in open_prs:
        stored_sha = await store.get_sha(repo_entry.repo, pr.number)

        if stored_sha == pr.head_sha:
            log.debug("pr_skipped_unchanged", repo=repo_entry.repo, pr_number=pr.number, sha=pr.head_sha)
            continue

        if stored_sha is None:
            diff_type = "full"
            before_sha = None
            log.info("pr_detected_new", repo=repo_entry.repo, pr_number=pr.number, head_sha=pr.head_sha)
        else:
            diff_type = "incremental"
            before_sha = stored_sha
            log.info(
                "pr_detected_updated",
                repo=repo_entry.repo,
                pr_number=pr.number,
                head_sha=pr.head_sha,
                before_sha=stored_sha,
            )

        review_tasks.append(
            run_review(
                repo=repo_entry.repo,
                pr_number=pr.number,
                head_sha=pr.head_sha,
                diff_type=diff_type,
                before_sha=before_sha,
            )
        )

    if review_tasks:
        await asyncio.gather(*review_tasks)
