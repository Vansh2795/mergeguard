"""MergeGuard: Cross-PR intelligence for the agentic coding era."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("py-mergeguard")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
