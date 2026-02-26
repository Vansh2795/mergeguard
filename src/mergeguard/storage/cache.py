"""File-based cache for AST/symbol indexes and PR data.

Caches analysis results to avoid redundant work across CI runs.
Uses file modification time and git SHA as cache invalidation keys.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class AnalysisCache:
    """File-based cache for MergeGuard analysis artifacts.

    Stores cached data as JSON files in a cache directory
    (typically .mergeguard-cache/).
    """

    def __init__(self, cache_dir: str | Path = ".mergeguard-cache"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        """Retrieve a cached value by key.

        Returns None if the key is not in the cache.
        """
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: dict) -> None:
        """Store a value in the cache."""
        path = self._key_to_path(key)
        with open(path, "w") as f:
            json.dump(value, f)

    def invalidate(self, key: str) -> None:
        """Remove a cached value."""
        path = self._key_to_path(key)
        path.unlink(missing_ok=True)

    def clear(self) -> None:
        """Remove all cached data."""
        for path in self._cache_dir.glob("*.json"):
            path.unlink()

    def make_key(self, *parts: str) -> str:
        """Create a cache key from multiple parts.

        Uses SHA-256 hash to create a filesystem-safe key.
        """
        combined = ":".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path."""
        # Sanitize key for filesystem
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self._cache_dir / f"{safe_key}.json"
