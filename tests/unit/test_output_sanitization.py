"""Tests for output sanitization in PR comments and annotations."""

from __future__ import annotations

from mergeguard.models import Conflict, ConflictSeverity, ConflictType
from mergeguard.output._sanitize import escape_backticks, sanitize_markdown


def _make_conflict(**overrides):
    defaults = dict(
        conflict_type=ConflictType.HARD,
        severity=ConflictSeverity.WARNING,
        source_pr=1,
        target_pr=2,
        file_path="src/main.py",
        description="Normal description",
        recommendation="Normal recommendation",
    )
    defaults.update(overrides)
    return Conflict(**defaults)


class TestSanitizeMarkdown:
    def test_escapes_html_tags(self):
        result = sanitize_markdown('<img src=x onerror="alert(1)">')
        assert "<img" not in result
        assert "&lt;img" in result

    def test_escapes_markdown_links(self):
        result = sanitize_markdown("Click [here](https://evil.com) for details")
        # Brackets should be escaped so markdown doesn't render a link
        assert "[here]" not in result
        assert r"\[here\]" in result

    def test_preserves_normal_text(self):
        result = sanitize_markdown("Normal description of a conflict")
        assert result == "Normal description of a conflict"


class TestEscapeBackticks:
    def test_escapes_backticks(self):
        result = escape_backticks("src/`injected`/main.py")
        assert "`injected`" not in result
        assert "\\`injected\\`" in result

    def test_preserves_normal_paths(self):
        result = escape_backticks("src/main.py")
        assert result == "src/main.py"


class TestCommentFormatting:
    def test_html_in_description_is_escaped_in_comment(self):
        from mergeguard.output.github_comment import _format_conflict_compact

        c = _make_conflict(description='<img src=x onerror="alert(1)">')
        result = _format_conflict_compact(c, "owner/repo")
        assert "<img" not in result

    def test_html_in_description_is_escaped_in_annotation(self):
        from mergeguard.output.inline_annotations import _format_annotation_body

        c = _make_conflict(description='<img src=x onerror="alert(1)">')
        result = _format_annotation_body(c, "owner/repo", "github")
        assert "<img" not in result
