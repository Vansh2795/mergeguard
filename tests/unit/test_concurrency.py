"""Concurrency tests for thread safety (T-2)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from unittest.mock import MagicMock

from mergeguard.analysis.symbol_index import SymbolIndex
from mergeguard.models import (
    ChangedFile,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
)


SAMPLE_PYTHON = """\
def greet(name):
    return f"Hello, {name}"

def farewell(name):
    return f"Goodbye, {name}"

class UserService:
    def get_user(self, user_id):
        pass

    def delete_user(self, user_id):
        pass
"""


def _make_pr(number: int, files: list[str]) -> PRInfo:
    pr = PRInfo(
        number=number,
        title=f"PR {number}",
        author="dev",
        base_branch="main",
        head_branch=f"branch-{number}",
        head_sha=f"sha{number}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    pr.changed_files = [
        ChangedFile(path=f, status=FileChangeStatus.MODIFIED) for f in files
    ]
    return pr


class TestThreadSafeSymbolIndex:
    """Concurrent get_symbols calls should not corrupt the cache."""

    def test_concurrent_get_symbols(self):
        index = SymbolIndex()
        errors: list[Exception] = []

        def worker(ref: str):
            try:
                symbols = index.get_symbols("service.py", SAMPLE_PYTHON, ref=ref)
                names = {s.name for s in symbols}
                assert "greet" in names
                assert "farewell" in names
            except Exception as exc:
                errors.append(exc)

        threads = []
        # Run many threads using the same ref (cache contention)
        for i in range(20):
            t = threading.Thread(target=worker, args=(f"ref-{i % 3}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_concurrent_get_symbols_and_call_graph(self):
        index = SymbolIndex()
        errors: list[Exception] = []

        def worker(ref: str):
            try:
                symbols, call_graph = index.get_symbols_and_call_graph(
                    "service.py", SAMPLE_PYTHON, ref=ref,
                )
                names = {s.name for s in symbols}
                assert "greet" in names
                assert isinstance(call_graph, dict)
            except Exception as exc:
                errors.append(exc)

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(f"ref-{i % 3}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"


class TestThreadSafeContentCache:
    """Concurrent _get_file_content_cached calls should not lose entries."""

    def test_concurrent_cache_access(self):
        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = {}
        engine._cache_lock = threading.Lock()

        call_count = {"n": 0}
        call_lock = threading.Lock()

        def mock_get_content(path, ref):
            with call_lock:
                call_count["n"] += 1
            return f"content-of-{path}-at-{ref}"

        engine._client = MagicMock()
        engine._client.get_file_content.side_effect = mock_get_content

        errors: list[Exception] = []

        def worker(file_idx: int):
            try:
                path = f"src/file{file_idx % 5}.py"
                result = engine._get_file_content_cached(path, "main")
                assert result == f"content-of-{path}-at-main"
            except Exception as exc:
                errors.append(exc)

        threads = []
        for i in range(30):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        # Cache should have exactly 5 entries (one per unique file)
        assert len(engine._content_cache) == 5


class TestParallelFetchAndEnrichPR:
    """Parallel _fetch_and_enrich_pr calls with overlapping files should not cause duplicate symbols."""

    def test_parallel_enrichment_no_duplicates(self):
        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._content_cache = {}
        engine._cache_lock = threading.Lock()
        engine._symbol_index = SymbolIndex()
        engine._config = MergeGuardConfig()
        engine._ignore_res = []
        engine._client = MagicMock()
        engine._client.get_pr_files.return_value = [
            ChangedFile(
                path="src/shared.py",
                status=FileChangeStatus.MODIFIED,
                additions=5, deletions=2,
                patch="@@ -1,5 +1,8 @@\n def greet(name):\n-    return 'hi'\n+    return f'Hello, {name}'\n",
            ),
        ]
        engine._client.get_file_content.return_value = SAMPLE_PYTHON
        engine._client.get_pr_diff.return_value = ""

        prs = [_make_pr(i, ["src/shared.py"]) for i in range(5)]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(engine._fetch_and_enrich_pr, pr) for pr in prs]
            for f in as_completed(futures, timeout=30):
                f.result()

        # Each PR should have symbols independently populated, no cross-contamination
        for pr in prs:
            # Symbols may or may not be populated depending on diff parsing,
            # but there should be no crash and no duplicate entries
            seen = set()
            for cs in pr.changed_symbols:
                key = (cs.symbol.file_path, cs.symbol.name)
                assert key not in seen, f"Duplicate symbol in PR #{pr.number}: {key}"
                seen.add(key)
