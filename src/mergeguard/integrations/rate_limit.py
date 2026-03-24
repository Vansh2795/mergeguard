"""Shared rate-limit checking for SCM HTTP clients."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


def check_rate_limit(
    response: httpx.Response,
    *,
    remaining_header: str = "X-RateLimit-Remaining",
    reset_header: str = "X-RateLimit-Reset",
) -> None:
    """Sleep if rate limit is nearly exhausted.

    Each SCM platform uses its own header names — callers pass the
    platform-specific names.
    """
    remaining = response.headers.get(remaining_header)
    if remaining is None:
        return
    remaining_int = int(remaining)
    if remaining_int < 10:
        reset_ts = response.headers.get(reset_header)
        if reset_ts:
            wait = max(0, int(reset_ts) - int(time.time()) + 1)
            if wait > 0:
                logger.warning(
                    "Rate limit low (%s remaining), sleeping %ds",
                    remaining,
                    wait,
                )
                time.sleep(min(wait, 30))
    elif remaining_int < 100:
        # Proportional backoff: linearly scale from 0s at 100 to ~2s at 10
        backoff = 2.0 * (100 - remaining_int) / 90
        if backoff > 0.1:
            logger.debug(
                "Rate limit approaching (%s remaining), sleeping %.1fs",
                remaining,
                backoff,
            )
            time.sleep(backoff)
