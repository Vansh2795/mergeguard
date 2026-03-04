"""Error recovery tests (T-3)."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mergeguard.models import (
    MergeGuardConfig,
    PRInfo,
)


def _make_pr(number: int) -> PRInfo:
    return PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=f"branch-{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestCorruptCacheJSON:
    """AnalysisCache.get() should return None for non-JSON / corrupt files."""

    def test_corrupt_json_returns_none(self, tmp_path):
        from mergeguard.storage.cache import AnalysisCache

        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        # Write corrupt data to a cache entry
        key = cache.make_key("owner/repo", "42", "sha123")
        path = cache._key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{{{{not valid json!!!!")

        result = cache.get(key)
        assert result is None

    def test_non_dict_json_returns_none(self, tmp_path):
        from mergeguard.storage.cache import AnalysisCache

        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        key = cache.make_key("owner/repo", "42", "sha456")
        path = cache._key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([1, 2, 3]))  # Valid JSON, but not a dict

        result = cache.get(key)
        assert result is None


class TestGitHubAPITimeoutDuringEnrichment:
    """_fetch_and_enrich_pr should log warning and not crash on timeout."""

    def test_timeout_handled_gracefully(self):
        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = {}
        engine._cache_lock = threading.Lock()
        engine._symbol_index = MagicMock()
        engine._config = MergeGuardConfig()
        engine._ignore_res = []
        engine._client = MagicMock()
        engine._client.get_pr_files.side_effect = httpx.ReadTimeout("timed out")

        pr = _make_pr(1)
        # Should not raise
        engine._fetch_and_enrich_pr(pr)
        # PR files should not be modified
        assert len(pr.changed_files) == 0


class TestDiskFullDuringCacheWrite:
    """AnalysisCache.set() should clean up tmp file on OSError."""

    def test_disk_full_raises_and_cleans_up(self, tmp_path):
        from mergeguard.storage.cache import AnalysisCache

        cache = AnalysisCache(cache_dir=tmp_path / "cache")
        key = cache.make_key("owner/repo", "42", "sha789")

        # Patch json.dump to raise OSError (simulating disk full during write)
        with (
            patch(
                "mergeguard.storage.cache.json.dump", side_effect=OSError("No space left on device")
            ),
            pytest.raises(OSError),
        ):
            cache.set(key, {"value": 42})

        # Verify no stale tmp files remain
        cache_dir = tmp_path / "cache"
        tmp_files = list(cache_dir.glob("*.tmp"))
        assert len(tmp_files) == 0
