"""Prompt assembler module — three-layer prompt assembly for the PR Review Bot."""

from __future__ import annotations

import os

from dolores_common.logging import get_logger

from .schemas import AgentsFile, DiffMetadata, EffectiveConfig

log = get_logger(__name__)
_base_prompt: str = ""
_verification_prompt: str = ""


def load_base_prompt(prompts_dir: str) -> str:
    """Read base_review.md from prompts_dir and store it as the module-level base prompt.

    Should be called once at app startup. Not re-read per poll cycle.
    """
    global _base_prompt
    path = os.path.join(prompts_dir, "base_review.md")
    with open(path) as f:
        _base_prompt = f.read()
    return _base_prompt


def load_verification_prompt(prompts_dir: str) -> str:
    """Read verification_review.md from prompts_dir and store it as module-level.

    Used during the second stage of the agentic review pipeline.
    """
    global _verification_prompt
    path = os.path.join(prompts_dir, "verification_review.md")
    try:
        with open(path) as f:
            _verification_prompt = f.read()
    except FileNotFoundError:
        log.warning("verification_prompt_not_found", path=path)
        _verification_prompt = ""
    return _verification_prompt


def assemble_prompt(
    config: EffectiveConfig,
    agents_files: list[AgentsFile],
    diff_text: str,
    diff_meta: DiffMetadata,
    verification_draft: str | None = None,
) -> list[dict]:
    """Build the LiteLLM messages list for a PR review.

    Assembly layers (in order):
      [1] Active prompt (system message):
            - mode="base"    → base prompt only
            - mode="extend"  → base prompt + per-repo extension appended
            - mode="replace" → per-repo extension only (base prompt absent)
            - If *verification_draft* is present, uses _verification_prompt instead.
      [2] AGENTS.md block (user message prefix): root first, then subdirectories
      [3] Full File Context (optional): The complete source code of changed files
      [4] Draft Review (optional): Present only during the verification stage
      [5] Diff text (user message suffix)

    Returns a list of dicts in LiteLLM messages format.
    """
    if verification_draft:
        active_prompt = _verification_prompt
    else:
        active_prompt = _build_active_prompt(config)

    user_content_parts: list[str] = []

    if agents_files:
        agents_block_lines: list[str] = ["# AGENTS.md Context\n"]
        for af in agents_files:
            agents_block_lines.append(f"## {af.path}\n\n{af.content}\n")
        user_content_parts.append("\n".join(agents_block_lines))

    # Add Full File Context
    file_context_lines: list[str] = ["# Full File Context\n"]
    file_context_lines.append(
        "The following blocks contain the FULL source code of the files changed in this PR (at the current head). "
        "Use this for deep analysis of data flow, memory management, and architectural consistency.\n"
    )
    for filename, file_data in diff_meta.files.items():
        if file_data.content:
            file_context_lines.append(f"## File: {filename}\n\n```\n{file_data.content}\n```\n")

    if len(file_context_lines) > 2:  # only add if we actually have content
        user_content_parts.append("\n".join(file_context_lines))

    # If verifying, include the draft
    if verification_draft:
        user_content_parts.append("# DRAFT REVIEW FOR VERIFICATION\n\n" + verification_draft)

    user_content_parts.append("# PR Diff\n" + diff_text)
    user_content = "\n\n".join(user_content_parts)

    # Log estimated token count (rough heuristic: 4 chars per token)
    total_chars = len(active_prompt) + len(user_content)
    log.info("prompt_assembled", repo=config.repo, estimated_tokens=total_chars // 4, char_count=total_chars)

    return [
        {"role": "system", "content": active_prompt},
        {"role": "user", "content": user_content},
    ]


def _build_active_prompt(config: EffectiveConfig) -> str:
    """Return the active prompt string based on prompt_mode."""
    if config.prompt_mode == "replace":
        return config.prompt_extension or _base_prompt

    if config.prompt_mode == "extend":
        extension = config.prompt_extension or ""
        return f"{_base_prompt}\n\n{extension}".rstrip()

    return _base_prompt
