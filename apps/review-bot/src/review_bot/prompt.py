"""Prompt assembler module — three-layer prompt assembly for the PR Review Bot."""

from __future__ import annotations

import os

from .schemas import AgentsFile, EffectiveConfig

_base_prompt: str = ""


def load_base_prompt(prompts_dir: str) -> str:
    """Read base_review.md from prompts_dir and store it as the module-level base prompt.

    Should be called once at app startup. Not re-read per poll cycle.
    """
    global _base_prompt
    path = os.path.join(prompts_dir, "base_review.md")
    with open(path) as f:
        _base_prompt = f.read()
    return _base_prompt


def assemble_prompt(
    config: EffectiveConfig,
    agents_files: list[AgentsFile],
    diff_text: str,
) -> list[dict]:
    """Build the LiteLLM messages list for a PR review.

    Assembly layers (in order):
      [1] Active prompt (system message):
            - mode="base"    → base prompt only
            - mode="extend"  → base prompt + per-repo extension appended
            - mode="replace" → per-repo extension only (base prompt absent)
      [2] AGENTS.md block (user message prefix): root first, then subdirectories
      [3] Diff text (user message suffix)

    Returns a list of dicts in LiteLLM messages format.
    """
    active_prompt = _build_active_prompt(config)

    user_content_parts: list[str] = []

    if agents_files:
        agents_block_lines: list[str] = ["# AGENTS.md Context\n"]
        for af in agents_files:
            agents_block_lines.append(f"## {af.path}\n\n{af.content}\n")
        user_content_parts.append("\n".join(agents_block_lines))

    user_content_parts.append(diff_text)

    return [
        {"role": "system", "content": active_prompt},
        {"role": "user", "content": "\n\n".join(user_content_parts)},
    ]


def _build_active_prompt(config: EffectiveConfig) -> str:
    """Return the active prompt string based on prompt_mode."""
    if config.prompt_mode == "replace":
        return config.prompt_extension or _base_prompt

    if config.prompt_mode == "extend":
        extension = config.prompt_extension or ""
        return f"{_base_prompt}\n\n{extension}".rstrip()

    return _base_prompt
