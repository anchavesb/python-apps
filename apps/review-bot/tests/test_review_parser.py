"""Tests for review_parser.py — parse_review behavior."""

from __future__ import annotations

import json

from review_bot.review_parser import parse_review
from review_bot.schemas import DiffFile, DiffMetadata


def _make_diff_metadata(*file_specs: tuple[str, list[int]]) -> DiffMetadata:
    """Build a DiffMetadata from (path, changed_lines) pairs."""
    files = {path: DiffFile(path=path, changed_lines=lines) for path, lines in file_specs}
    return DiffMetadata(files=files)


_MODEL = "gemini/gemini-2.0-flash"
_ATTRIBUTION_PREFIX = f"> Automated review by review-bot | Model: {_MODEL}"


class TestParseReviewValidJson:
    def test_valid_json_inline_comment_in_diff(self):
        diff = _make_diff_metadata(("src/foo.py", [10, 11, 12]))
        raw = json.dumps(
            {
                "summary": "Looks good overall.",
                "comments": [{"path": "src/foo.py", "line": 11, "body": "Use a constant here."}],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert len(result.inline_comments) == 1
        comment = result.inline_comments[0]
        assert comment.path == "src/foo.py"
        assert comment.line == 11
        assert comment.body.startswith(_ATTRIBUTION_PREFIX)
        assert "Use a constant here." in comment.body

    def test_summary_prefixed_with_attribution(self):
        diff = _make_diff_metadata(("src/foo.py", [5]))
        raw = json.dumps({"summary": "All checks passed.", "comments": []})

        result = parse_review(raw, diff, _MODEL)

        assert result.summary.startswith(_ATTRIBUTION_PREFIX)
        assert "All checks passed." in result.summary

    def test_multiple_valid_comments_all_included(self):
        diff = _make_diff_metadata(("a.py", [1, 2, 3]), ("b.py", [7, 8]))
        raw = json.dumps(
            {
                "summary": "Two files reviewed.",
                "comments": [
                    {"path": "a.py", "line": 2, "body": "Comment A"},
                    {"path": "b.py", "line": 8, "body": "Comment B"},
                ],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert len(result.inline_comments) == 2
        paths = {c.path for c in result.inline_comments}
        assert paths == {"a.py", "b.py"}


class TestParseReviewLineDemotion:
    def test_out_of_diff_line_demoted_to_footnote(self):
        diff = _make_diff_metadata(("src/foo.py", [10, 11, 12]))
        raw = json.dumps(
            {
                "summary": "Minor issue found.",
                "comments": [{"path": "src/foo.py", "line": 99, "body": "Wrong line."}],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert result.inline_comments == []
        assert "src/foo.py:99" in result.summary
        assert "Wrong line." in result.summary

    def test_unknown_file_path_demoted_to_footnote(self):
        diff = _make_diff_metadata(("src/foo.py", [5]))
        raw = json.dumps(
            {
                "summary": "Issue in unknown file.",
                "comments": [{"path": "src/other.py", "line": 5, "body": "Not in diff."}],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert result.inline_comments == []
        assert "src/other.py:5" in result.summary
        assert "Not in diff." in result.summary

    def test_mixed_valid_and_invalid_comments(self):
        diff = _make_diff_metadata(("a.py", [3, 4, 5]))
        raw = json.dumps(
            {
                "summary": "Mixed comments.",
                "comments": [
                    {"path": "a.py", "line": 4, "body": "Valid comment."},
                    {"path": "a.py", "line": 99, "body": "Invalid line."},
                ],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert len(result.inline_comments) == 1
        assert result.inline_comments[0].line == 4
        assert "a.py:99" in result.summary
        assert "Invalid line." in result.summary

    def test_footnote_section_not_present_when_all_valid(self):
        diff = _make_diff_metadata(("a.py", [1]))
        raw = json.dumps(
            {
                "summary": "Clean.",
                "comments": [{"path": "a.py", "line": 1, "body": "Nice."}],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert "could not be placed inline" not in result.summary


class TestParseReviewMalformedJson:
    def test_malformed_json_returns_summary_only(self):
        diff = _make_diff_metadata(("src/foo.py", [1]))

        result = parse_review("this is not json {{{", diff, _MODEL)

        assert result.inline_comments == []
        assert result.summary.startswith(_ATTRIBUTION_PREFIX)
        assert "inline comments could not be parsed" in result.summary

    def test_empty_string_treated_as_malformed(self):
        diff = _make_diff_metadata()

        result = parse_review("", diff, _MODEL)

        assert result.inline_comments == []
        assert "inline comments could not be parsed" in result.summary


class TestParseReviewAttribution:
    def test_inline_comment_body_prefixed_with_attribution(self):
        diff = _make_diff_metadata(("file.py", [1]))
        raw = json.dumps(
            {
                "summary": "Summary text.",
                "comments": [{"path": "file.py", "line": 1, "body": "The body."}],
            }
        )

        result = parse_review(raw, diff, _MODEL)

        assert result.inline_comments[0].body.startswith(_ATTRIBUTION_PREFIX)

    def test_model_id_appears_in_attribution(self):
        model = "anthropic/claude-sonnet-4-20250514"
        diff = _make_diff_metadata(("f.py", [2]))
        raw = json.dumps(
            {
                "summary": "s",
                "comments": [{"path": "f.py", "line": 2, "body": "b"}],
            }
        )

        result = parse_review(raw, diff, model)

        expected_header = f"> Automated review by review-bot | Model: {model}"
        assert result.summary.startswith(expected_header)
        assert result.inline_comments[0].body.startswith(expected_header)
