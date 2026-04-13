"""Shared review pipeline — run_review() coroutine and asyncio.Semaphore management.

Both the polling loop (poller.py) and the manual trigger route (routes.py) call
run_review() and share the same module-level semaphore so the total number of
concurrent LLM calls is bounded regardless of trigger source.
"""

from __future__ import annotations

import asyncio
import time

from dolores_common.logging import get_logger

from .agents_discovery import discover_agents_md
from .config import resolve_effective_config
from .github_client import fetch_file_contents, get_diff, post_review
from .llm_client import call_llm
from .prompt import assemble_prompt
from .review_parser import parse_review
from .schemas import DiffFile
from .state_store import get_state_store

log = get_logger(__name__)

_semaphore: asyncio.Semaphore | None = None
MAX_DISCOVERY_ROUNDS = 2


def init_semaphore(max_concurrent: int) -> None:
    """Create the module-level semaphore. Must be called once at app lifespan."""
    global _semaphore
    _semaphore = asyncio.Semaphore(max_concurrent)


def get_semaphore() -> asyncio.Semaphore:
    """Return the shared semaphore; raises RuntimeError if not yet initialised."""
    if _semaphore is None:
        raise RuntimeError("Semaphore not initialized — call init_semaphore() first")
    return _semaphore


async def run_review(
    repo: str,
    pr_number: int,
    head_sha: str,
    diff_type: str,
    before_sha: str | None,
) -> None:
    """Execute the full PR review pipeline under the shared concurrency semaphore.

    Args:
        repo: Repository in ``owner/repo`` form.
        pr_number: Pull request number.
        head_sha: Current head commit SHA of the PR.
        diff_type: ``"full"`` for new PRs; ``"incremental"`` for updated ones.
        before_sha: Previous head SHA — required when diff_type is ``"incremental"``.
    """
    sem = get_semaphore()
    start = time.monotonic()

    log.info("review_start", repo=repo, pr_number=pr_number, diff_type=diff_type)

    try:
        async with sem:
            owner, name = repo.split("/", 1)
            # Preliminary resolution to obtain the GitHub token for fetching
            # the per-repo .github/review-bot.yml (Layer 1 config).
            preliminary = resolve_effective_config(repo)
            store = get_state_store()

            # Layer 1 — fetch per-repo config from the default branch.
            # Returns None on 404; resolve_effective_config handles None gracefully.
            per_repo_yml = await fetch_file_contents(
                owner, name, ".github/review-bot.yml", "HEAD", preliminary.github_token
            )

            effective = resolve_effective_config(repo, per_repo_yml)

            diff_text, diff_meta = await get_diff(
                owner,
                name,
                pr_number,
                diff_type,
                before_sha=before_sha,
                after_sha=head_sha,
                token=effective.github_token,
            )
            agents_files = await discover_agents_md(
                owner,
                name,
                list(diff_meta.files.keys()),
                head_sha,
                effective.github_token,
            )

            # --- Agentic Discovery Loop (Stage 1) ---
            discovery_round = 0
            discovered_paths: set[str] = set()
            raw_response = ""

            while True:
                messages = assemble_prompt(effective, agents_files, diff_text, diff_meta)
                raw_response = await call_llm(effective.model, messages, effective.api_key)
                result = parse_review(raw_response, diff_meta, effective.model)

                # Are there new files we need to fetch?
                new_files = [f for f in result.required_files if f not in diff_meta.files and f not in discovered_paths]

                if not new_files or discovery_round >= MAX_DISCOVERY_ROUNDS:
                    break

                discovery_round += 1
                log.info(
                    "discovery_round_fetching",
                    repo=repo,
                    pr_number=pr_number,
                    round=discovery_round,
                    files=new_files,
                )

                for path in new_files:
                    discovered_paths.add(path)
                    content = await fetch_file_contents(owner, name, path, head_sha, effective.github_token)
                    if content:
                        # Inject into diff_meta so it appears in the next prompt's Full File Context
                        diff_meta.files[path] = DiffFile(path=path, changed_lines=[], content=content)

            # Stage 2: Verification Pass (Optional)
            final_result = result
            if effective.verification_mode:
                log.info("verification_pass_start", repo=repo, pr_number=pr_number)
                verify_messages = assemble_prompt(
                    effective, agents_files, diff_text, diff_meta, verification_draft=raw_response
                )
                raw_verify = await call_llm(effective.model, verify_messages, effective.api_key)
                final_result = parse_review(raw_verify, diff_meta, effective.model)

            await post_review(owner, name, pr_number, final_result, effective.github_token)
            await store.set_sha(repo, pr_number, head_sha)

            elapsed = round(time.monotonic() - start, 3)
            log.info(
                "review_posted",
                repo=repo,
                pr_number=pr_number,
                diff_type=diff_type,
                elapsed_seconds=elapsed,
            )
    except Exception:
        elapsed = round(time.monotonic() - start, 3)
        log.exception(
            "review_error",
            repo=repo,
            pr_number=pr_number,
            diff_type=diff_type,
            elapsed_seconds=elapsed,
        )
        raise
