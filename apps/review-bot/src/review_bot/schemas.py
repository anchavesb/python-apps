"""Pydantic models for the review-bot service."""

from __future__ import annotations

from pydantic import BaseModel


class PRInfo(BaseModel):
    number: int
    title: str
    head_sha: str
    owner: str
    repo: str


class InlineComment(BaseModel):
    path: str
    line: int
    body: str


class ReviewResult(BaseModel):
    thought: str | None = None
    summary: str
    inline_comments: list[InlineComment] = []


class DiffFile(BaseModel):
    path: str
    changed_lines: list[int]


class DiffMetadata(BaseModel):
    files: dict[str, DiffFile]


class EffectiveConfig(BaseModel):
    """Resolved, per-repo configuration used throughout the review pipeline."""

    repo: str
    model: str
    prompt_mode: str = "base"
    prompt_extension: str | None = None
    api_key: str
    github_token: str


class AgentsFile(BaseModel):
    path: str
    content: str


class ReviewRequest(BaseModel):
    repo: str
    pr_number: int
    force: bool = False


class ReviewAccepted(BaseModel):
    status: str = "accepted"
    repo: str
    pr_number: int
    head_sha: str


class ReviewSkipped(BaseModel):
    status: str = "skipped"
    repo: str
    pr_number: int
    sha: str
