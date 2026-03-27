"""Review parser — transform raw LLM JSON output into a validated ReviewResult.

Public API
----------
- ``parse_review`` — entry point; parses, validates, and annotates LLM output.
"""

from __future__ import annotations

import json

from dolores_common.logging import get_logger

from .schemas import DiffMetadata, InlineComment, ReviewResult

log = get_logger(__name__)


def _attribution_header(model_id: str) -> str:
    return f"> Automated review by review-bot | Model: {model_id}"


def parse_review(raw_response: str, diff_metadata: DiffMetadata, model_id: str) -> ReviewResult:
    """Parse the LLM's raw JSON response into a validated ReviewResult.

    Steps:
    1. JSON-parse ``raw_response``; on failure return a summary-only result with a
       parse-failure note.
    2. Validate each inline comment's ``line`` against
       ``diff_metadata.files[path].changed_lines``; comments with lines outside the
       diff are demoted to summary footnotes rather than silently dropped.
    3. Prefix every ``summary`` and every ``inline_comment.body`` with the bot
       attribution blockquote (design §3.12).

    Args:
        raw_response: Raw string returned by the LLM (expected to be JSON).
        diff_metadata: Per-file changed-line metadata built from the PR diff.
        model_id: Model identifier string used in the attribution header.

    Returns:
        A ``ReviewResult`` with validated inline comments and an annotated summary.
    """
    header = _attribution_header(model_id)

    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, ValueError):
        log.warning("review_parser_malformed_json", model_id=model_id)
        summary = f"{header}\n\nNote: inline comments could not be parsed (malformed JSON response)."
        return ReviewResult(summary=summary, inline_comments=[])

    raw_summary: str = data.get("summary", "")
    raw_comments: list[dict] = data.get("comments", [])

    valid_comments: list[InlineComment] = []
    demoted_footnotes: list[str] = []

    for comment in raw_comments:
        path: str = comment.get("path", "")
        line = comment.get("line")
        body: str = comment.get("body", "")

        diff_file = diff_metadata.files.get(path)
        line_valid = diff_file is not None and line in diff_file.changed_lines

        if line_valid:
            valid_comments.append(
                InlineComment(
                    path=path,
                    line=line,
                    body=f"{header}\n\n{body}",
                )
            )
        else:
            log.debug(
                "review_parser_line_demoted",
                path=path,
                line=line,
                model_id=model_id,
            )
            demoted_footnotes.append(f"- `{path}:{line}`: {body}")

    summary_parts = [f"{header}\n\n{raw_summary}"]
    if demoted_footnotes:
        footnote_block = "\n".join(demoted_footnotes)
        summary_parts.append(
            "\n\n**Note**: The following comments reference lines not present in the diff "
            "and could not be placed inline:\n" + footnote_block
        )

    return ReviewResult(
        summary="".join(summary_parts),
        inline_comments=valid_comments,
    )
