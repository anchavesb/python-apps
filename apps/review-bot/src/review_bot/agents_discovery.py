"""AGENTS.md discovery module — fetch AGENTS.md files from a GitHub repo via the Contents API."""

from __future__ import annotations

from .github_client import fetch_file_contents
from .schemas import AgentsFile


async def discover_agents_md(
    owner: str,
    repo: str,
    diff_file_paths: list[str],
    head_sha: str,
    token: str,
) -> list[AgentsFile]:
    """Discover AGENTS.md files relevant to the given diff.

    Always attempts the root AGENTS.md. For each unique top-level directory prefix
    found in diff_file_paths, also attempts <prefix>/AGENTS.md.

    Root file is returned first; subdirectory files follow in sorted order.

    Returns an empty list without error if no AGENTS.md files are found.
    """
    results: list[AgentsFile] = []

    root_content = await fetch_file_contents(owner, repo, "AGENTS.md", head_sha, token)
    if root_content is not None:
        results.append(AgentsFile(path="AGENTS.md", content=root_content))

    prefixes: set[str] = set()
    for path in diff_file_paths:
        parts = path.split("/", 2)
        if len(parts) > 2:
            prefixes.add("/".join(parts[:2]))

    for prefix in sorted(prefixes):
        candidate = f"{prefix}/AGENTS.md"
        content = await fetch_file_contents(owner, repo, candidate, head_sha, token)
        if content is not None:
            results.append(AgentsFile(path=candidate, content=content))

    return results
