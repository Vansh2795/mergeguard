"""Tests for SVG badge generation."""

from __future__ import annotations

from mergeguard.output.badge import _render_svg


class TestSVGEscape:
    def test_value_with_angle_brackets_is_escaped(self):
        svg = _render_svg("MergeGuard", "<script>alert(1)</script>", "#4c1")
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_value_with_ampersand_is_escaped(self):
        svg = _render_svg("MergeGuard", "foo&bar", "#4c1")
        assert "&amp;" in svg

    def test_label_with_angle_brackets_is_escaped(self):
        svg = _render_svg("<img>", "safe", "#4c1")
        assert "<img>" not in svg
        assert "&lt;img&gt;" in svg

    def test_normal_value_renders(self):
        svg = _render_svg("MergeGuard", "3 conflicts", "#e05d44")
        assert "3 conflicts" in svg
