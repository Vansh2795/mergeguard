"""Tests for rate limit checking."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from mergeguard.integrations.rate_limit import check_rate_limit


def _make_response(remaining: str | None = None, reset: str | None = None) -> httpx.Response:
    headers: dict[str, str] = {}
    if remaining is not None:
        headers["X-RateLimit-Remaining"] = remaining
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    return httpx.Response(
        200, headers=headers, request=httpx.Request("GET", "https://api.example.com")
    )


class TestCheckRateLimit:
    def test_no_header_returns_silently(self):
        resp = _make_response()
        check_rate_limit(resp)

    def test_non_numeric_remaining_does_not_crash(self):
        resp = _make_response(remaining="unlimited")
        check_rate_limit(resp)

    def test_empty_remaining_does_not_crash(self):
        resp = _make_response(remaining="")
        check_rate_limit(resp)

    def test_high_remaining_no_sleep(self):
        resp = _make_response(remaining="5000")
        with patch("mergeguard.integrations.rate_limit.time.sleep") as mock_sleep:
            check_rate_limit(resp)
            mock_sleep.assert_not_called()

    def test_low_remaining_triggers_backoff(self):
        resp = _make_response(remaining="50")
        with patch("mergeguard.integrations.rate_limit.time.sleep") as mock_sleep:
            check_rate_limit(resp)
            mock_sleep.assert_called_once()
            wait = mock_sleep.call_args[0][0]
            assert 0 < wait < 2.5
