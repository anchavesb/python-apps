"""GitHub REST API client for review-bot.

Wraps a shared ``httpx.AsyncClient`` singleton.  The singleton is initialised
once at app lifespan via :func:`set_github_client` and retrieved everywhere
else via :func:`get_github_client`.

Public API
----------
- ``set_github_client`` / ``get_github_client`` — DI initialiser / getter
- ``list_open_prs`` — enumerate open PRs for a repository
- ``get_pr_info`` — fetch a single PR's current metadata (head SHA, title)
- ``get_diff`` — fetch a diff in full or incremental mode
- ``fetch_file_contents`` — download a file at a specific ref; ``None`` on 404
- ``post_review`` — submit a GitHub Review with inline comments + summary
"""

from __future__ import annotations

import base64
import re
from typing import Literal

import httpx
from fastapi import HTTPException

from dolores_common.logging import get_logger

from .schemas import DiffFile, DiffMetadata, PRInfo, ReviewResult

log = get_logger(__name__)

_GITHUB_API = "https://api.github.com"

_client: httpx.AsyncClient | None = None


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


def set_github_client(client: httpx.AsyncClient) -> None:
    """Bind the shared httpx.AsyncClient at app lifespan."""
    global _client
    _client = client


def get_github_client() -> httpx.AsyncClient:
    """Return the shared client, raising HTTP 503 if not yet initialised."""
    if _client is None:
        raise HTTPException(status_code=503, detail="GitHub client not initialised")
    return _client


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    token = token.strip()
    if not token:
        log.warning("github_token_missing")
    else:
        log.info("github_token_present", length=len(token))
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _check_rate_limit(response: httpx.Response) -> None:
    """Log a structured WARNING when GitHub rate-limit headroom falls below 20 %."""
    try:
        remaining_str = response.headers.get("X-RateLimit-Remaining")
        limit_str = response.headers.get("X-RateLimit-Limit")
        if remaining_str is None or limit_str is None:
            return
        remaining = int(remaining_str)
        limit = int(limit_str)
        if limit <= 0:
            return
        if remaining < limit * 0.20:
            reset_ts = response.headers.get("X-RateLimit-Reset", "unknown")
            log.warning(
                "github_rate_limit_low",
                remaining=remaining,
                limit=limit,
                reset_at=reset_ts,
            )
    except (ValueError, AttributeError):
        pass


def _parse_changed_lines_from_patch(patch: str) -> list[int]:
    """Return new-file line numbers of every added line in a unified diff patch."""
    changed_lines: list[int] = []
    current_line = 0
    for raw_line in patch.splitlines():
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,\d+)?", raw_line)
            if match:
                current_line = int(match.group(1)) - 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            changed_lines.append(current_line)
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            pass  # deleted lines do not shift new-file numbering
        else:
            current_line += 1
    return changed_lines


def _parse_diff_metadata_from_text(diff_text: str) -> DiffMetadata:
    """Parse a raw unified diff into per-file changed-line metadata."""
    files: dict[str, DiffFile] = {}
    current_file: str | None = None
    current_line = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            # "diff --git a/path b/path" — use the b/ side as canonical path
            parts = raw_line.split(" b/", 1)
            current_file = parts[1].strip() if len(parts) == 2 else None
            current_line = 0
            if current_file and current_file not in files:
                files[current_file] = DiffFile(path=current_file, changed_lines=[])
        elif raw_line.startswith("@@") and current_file:
            match = re.search(r"\+(\d+)(?:,\d+)?", raw_line)
            if match:
                current_line = int(match.group(1)) - 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++") and current_file:
            current_line += 1
            files[current_file].changed_lines.append(current_line)
        elif raw_line.startswith("-") and not raw_line.startswith("---") and current_file:
            pass
        elif raw_line.startswith(" ") and current_file:
            current_line += 1

    return DiffMetadata(files=files)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_open_prs(owner: str, repo: str, token: str) -> list[PRInfo]:
    """Return open pull requests for ``owner/repo``."""
    client = get_github_client()
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls"
    try:
        response = await client.get(
            url,
            params={"state": "open", "per_page": 100},
            headers=_auth_headers(token),
        )
        _check_rate_limit(response)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("github_list_prs_http_error", owner=owner, repo=repo, status=exc.response.status_code, error=str(exc))
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc
    except httpx.RequestError as exc:
        log.error("github_list_prs_network_error", owner=owner, repo=repo, error=str(exc))
        raise HTTPException(status_code=502, detail=f"GitHub API network error: {exc}") from exc
    except Exception as exc:
        log.exception("github_list_prs_unexpected_error", owner=owner, repo=repo)
        raise exc

    prs = []
    for item in response.json():
        prs.append(
            PRInfo(number=item["number"], head_sha=item["head"]["sha"], title=item["title"], owner=owner, repo=repo)
        )
    return prs


async def get_pr_info(owner: str, repo: str, pr_number: int, token: str) -> PRInfo:
    """Return metadata for a single pull request, including its current head SHA."""
    client = get_github_client()
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
    try:
        response = await client.get(url, headers=_auth_headers(token))
        _check_rate_limit(response)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found in {owner}/{repo}")
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

    item = response.json()
    return PRInfo(number=item["number"], head_sha=item["head"]["sha"], title=item["title"], owner=owner, repo=repo)


async def get_diff(
    owner: str,
    repo: str,
    pr_number: int,
    mode: Literal["full", "incremental"],
    before_sha: str | None,
    after_sha: str | None,
    token: str,
) -> tuple[str, DiffMetadata]:
    """Fetch a PR diff and extract per-file changed-line metadata.

    ``mode="full"``
        Uses ``GET /repos/{o}/{r}/pulls/{n}/files`` (paginated).  Reconstructs
        a unified diff string from the ``patch`` field of each file entry.

    ``mode="incremental"``
        Uses ``GET /repos/{o}/{r}/compare/{before}...{after}`` with the
        ``application/vnd.github.diff`` accept header to retrieve a raw diff.
    """
    client = get_github_client()

    if mode == "full":
        diff_parts: list[str] = []
        files_meta: dict[str, DiffFile] = {}
        page = 1

        while True:
            url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
            try:
                response = await client.get(
                    url,
                    params={"page": page, "per_page": 100},
                    headers=_auth_headers(token),
                )
                _check_rate_limit(response)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

            batch = response.json()
            for file_entry in batch:
                filename: str = file_entry["filename"]
                patch: str = file_entry.get("patch", "")
                diff_parts.append(f"diff --git a/{filename} b/{filename}\n{patch}")
                changed = _parse_changed_lines_from_patch(patch) if patch else []
                files_meta[filename] = DiffFile(path=filename, changed_lines=changed)

            if len(batch) < 100:
                break
            page += 1

        diff_text = "\n".join(diff_parts)
        return diff_text, DiffMetadata(files=files_meta)

    else:  # incremental
        if before_sha is None or after_sha is None:
            raise ValueError("before_sha and after_sha are required for incremental mode")

        url = f"{_GITHUB_API}/repos/{owner}/{repo}/compare/{before_sha}...{after_sha}"
        headers = {**_auth_headers(token), "Accept": "application/vnd.github.diff"}
        try:
            response = await client.get(url, headers=headers)
            _check_rate_limit(response)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

        diff_text = response.text
        return diff_text, _parse_diff_metadata_from_text(diff_text)


async def fetch_file_contents(owner: str, repo: str, path: str, ref: str, token: str) -> str | None:
    """Download ``path`` at ``ref`` from ``owner/repo``; returns ``None`` on 404."""
    client = get_github_client()
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    try:
        response = await client.get(url, params={"ref": ref}, headers=_auth_headers(token))
        _check_rate_limit(response)
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

    data = response.json()
    encoded: str = data["content"].replace("\n", "")
    return base64.b64decode(encoded).decode("utf-8")


async def post_review(owner: str, repo: str, pr_number: int, result: ReviewResult, token: str) -> None:
    """Submit a GitHub Review with inline comments and a top-level summary body."""
    client = get_github_client()
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

    comments = [{"path": c.path, "line": c.line, "side": "RIGHT", "body": c.body} for c in result.inline_comments]
    payload = {
        "body": result.summary,
        "event": "COMMENT",
        "comments": comments,
    }

    try:
        response = await client.post(url, json=payload, headers=_auth_headers(token))
        _check_rate_limit(response)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

    log.info("github_review_posted", owner=owner, repo=repo, pr_number=pr_number, comments=len(comments))
