"""Markdown sanitization for user-facing output."""

from __future__ import annotations


def sanitize_markdown(text: str) -> str:
    """Neutralize markdown control characters in untrusted text."""
    # Escape HTML tags
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Escape markdown link brackets
    text = text.replace("[", r"\[").replace("]", r"\]")
    return text


def escape_backticks(text: str) -> str:
    """Escape backticks in text destined for inline code spans."""
    return text.replace("`", "\\`")
