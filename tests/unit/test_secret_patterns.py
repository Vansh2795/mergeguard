"""Tests for secret pattern regex safety."""

from __future__ import annotations

import re
import time

from mergeguard.core.secret_patterns import BUILTIN_PATTERNS


def _find_pattern(name: str) -> str:
    for p in BUILTIN_PATTERNS:
        if p.name == name:
            return p.pattern
    raise ValueError(f"Pattern not found: {name}")


class TestReDoSSafety:
    """Verify patterns complete in bounded time on adversarial input."""

    def test_heroku_pattern_bounded_on_long_input(self):
        pattern = _find_pattern("Heroku API Key")
        adversarial = "heroku" + "A" * 5000 + "ZZZZZZZZ"
        start = time.monotonic()
        re.search(pattern, adversarial)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Heroku pattern took {elapsed:.2f}s — possible ReDoS"

    def test_slack_token_pattern_bounded_on_long_input(self):
        pattern = _find_pattern("Slack Token")
        adversarial = "xoxb-" + "a" * 5000 + "!"
        start = time.monotonic()
        re.search(pattern, adversarial)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"Slack pattern took {elapsed:.2f}s — possible ReDoS"

    def test_heroku_still_detects_real_key(self):
        pattern = _find_pattern("Heroku API Key")
        real = "HEROKU_API_KEY=12345678-1234-1234-1234-123456789ABC"
        assert re.search(pattern, real) is not None

    def test_slack_still_detects_real_token(self):
        pattern = _find_pattern("Slack Token")
        real = "xoxb-1234567890-abcdefghij"
        assert re.search(pattern, real) is not None
