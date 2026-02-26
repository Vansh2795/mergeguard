"""SVG badge generator for risk scores.

Generates shields.io-compatible SVG badges that can be
embedded in README files or PR comments.
"""

from __future__ import annotations


def generate_risk_badge(risk_score: float) -> str:
    """Generate an SVG badge showing the risk score.

    Args:
        risk_score: Risk score between 0 and 100.

    Returns:
        SVG string for the badge.
    """
    color = _score_to_color(risk_score)
    label = "MergeGuard"
    value = f"{risk_score:.0f}/100"

    return _render_svg(label, value, color)


def generate_status_badge(status: str) -> str:
    """Generate a status badge (pass/warn/fail).

    Args:
        status: One of "pass", "warn", "fail".

    Returns:
        SVG string for the badge.
    """
    colors = {
        "pass": "#4c1",
        "warn": "#dfb317",
        "fail": "#e05d44",
    }
    color = colors.get(status, "#9f9f9f")
    return _render_svg("MergeGuard", status, color)


def _score_to_color(score: float) -> str:
    """Map a risk score to a badge color."""
    if score >= 70:
        return "#e05d44"  # Red
    if score >= 40:
        return "#dfb317"  # Yellow
    return "#4c1"  # Green


def _render_svg(label: str, value: str, color: str) -> str:
    """Render a shields.io-style SVG badge."""
    label_width = len(label) * 7 + 10
    value_width = len(value) * 7 + 10
    total_width = label_width + value_width

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_width / 2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_width / 2}" y="14">{label}</text>
    <text x="{label_width + value_width / 2}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{label_width + value_width / 2}" y="14">{value}</text>
  </g>
</svg>"""
