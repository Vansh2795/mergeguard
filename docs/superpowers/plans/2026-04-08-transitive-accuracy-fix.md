# Transitive Conflict Accuracy Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate false positive explosion in transitive conflict detection by requiring symbol-level evidence, limiting dependency depth, and removing ambiguous module name forms.

**Architecture:** Three independent fixes, each reducing false positives at a different stage of the pipeline: (1) trim module name generation to remove ambiguous short forms, (2) reduce BFS depth from 5 to 1 (direct imports only), (3) require symbol overlap for WARNING severity and skip conflicts with zero evidence. A new config field `max_transitive_depth` makes the depth configurable.

**Tech Stack:** Python 3.12+, pytest, Pydantic V2

---

## File Map

| File | Action | Task |
|------|--------|------|
| `src/mergeguard/core/engine.py:645-670` | Modify (`_file_path_module_forms`) | 1 |
| `src/mergeguard/analysis/dependency.py:83` | Modify (`get_dependents` default) | 2 |
| `src/mergeguard/models.py:536` | Modify (add `max_transitive_depth` config) | 2 |
| `src/mergeguard/core/engine.py:820-822` | Modify (pass depth config to `get_dependents`) | 2 |
| `src/mergeguard/core/engine.py:845-888` | Modify (severity logic in Direction A) | 3 |
| `src/mergeguard/core/engine.py:913-941` | Modify (severity logic in Direction B) | 3 |
| `tests/unit/test_engine.py:338-679` | Modify (update test expectations) | 4 |
| `benchmarks/run_benchmarks.py` | Modify (fix Windows encoding crash) | 5 |

---

### Task 1: Trim `_file_path_module_forms` to remove ambiguous forms

The current function generates single-segment names (`"conflict"`, `"core"`) and package-level forms (`"fastapi"`, `"mergeguard.core"`) that create false edges in the dependency graph. A file `fastapi/staticfiles.py` generates `"fastapi"` which matches `from fastapi import FastAPI` — but `FastAPI` is defined in `__init__.py`, not `staticfiles.py`.

**Files:**
- Modify: `src/mergeguard/core/engine.py:645-670`

- [ ] **Step 1: Remove single-segment and package-level forms**

Replace the `_file_path_module_forms` method in `src/mergeguard/core/engine.py` (lines 645-670):

```python
    @staticmethod
    def _file_path_module_forms(file_path: str) -> list[str]:
        """Convert a .py file path to dotted module name forms.

        Given ``src/mergeguard/core/conflict.py``, returns::

            ["src.mergeguard.core.conflict", "mergeguard.core.conflict",
             "core.conflict"]

        Single-segment forms (e.g., "conflict") and package-level forms
        (e.g., "mergeguard.core") are excluded because they create
        ambiguous matches in the dependency graph — a bare "conflict"
        could match unrelated imports, and "fastapi" as a package form
        would match imports from __init__.py, not the specific file.

        Returns an empty list for non-Python files.
        """
        if not file_path.endswith(".py"):
            return []
        parts = list(PurePosixPath(file_path).with_suffix("").parts)
        # Only include forms with 2+ segments to avoid ambiguous matches
        forms = [".".join(parts[i:]) for i in range(len(parts)) if len(parts) - i >= 2]
        return forms
```

- [ ] **Step 2: Run tests to see what breaks**

Run: `uv run pytest tests/unit/test_engine.py -k "transitive" -v`

Tests using single-segment module names as graph edge targets (e.g., `"models"`) will still pass because edges are stored under the target key in the graph's `_reverse` dict. Module forms are only used to look UP dependents from changed file paths. However, `test_via_module_name_form` (line 438) tests matching via short forms — read the test and update if needed.

- [ ] **Step 3: Commit**

```bash
git add src/mergeguard/core/engine.py
git commit -m "fix: remove ambiguous single-segment and package-level module forms

Single-segment forms like 'conflict' and package forms like 'fastapi'
create false edges in the dependency graph, causing transitive conflict
explosion in large repos."
```

---

### Task 2: Reduce dependency traversal depth to direct imports only

The 5-hop BFS in `get_dependents` reaches nearly the entire connected component in any well-connected codebase. Transitive conflicts beyond direct imports (depth 1) are redundant — if A→B→C, the A↔B conflict is already detected directly, so A↔C adds no new information.

**Files:**
- Modify: `src/mergeguard/models.py` (add config field after `max_transitive_per_pair`)
- Modify: `src/mergeguard/core/engine.py:820-822` (pass depth to get_dependents)

- [ ] **Step 1: Add `max_transitive_depth` config field**

In `src/mergeguard/models.py`, after `max_transitive_per_pair: int = 5`, add:

```python
    max_transitive_depth: int = 1  # BFS depth for transitive dependency traversal
```

- [ ] **Step 2: Pass config depth to `get_dependents` calls**

In `src/mergeguard/core/engine.py`, modify the `_cached_get_dependents` closure (around line 820):

```python
        max_depth = self._config.max_transitive_depth

        def _cached_get_dependents(path: str) -> set[str]:
            if path not in _dep_cache:
                _dep_cache[path] = graph.get_dependents(path, max_depth=max_depth)
            return _dep_cache[path]
```

Direction B calls already use `_cached_get_dependents` so they get the new depth automatically.

- [ ] **Step 3: Update `_make_engine` in tests**

In `tests/unit/test_engine.py`, in the `_make_engine` method (line 340), add:

```python
        engine._config.max_transitive_depth = 1
```

- [ ] **Step 4: Fix `test_deep_chain`**

Set `engine._config.max_transitive_depth = 2` in `test_deep_chain` (line 571) since it specifically tests 2-hop chain detection:

```python
    def test_deep_chain(self):
        engine = self._make_engine()
        engine._config.max_transitive_depth = 2  # This test needs 2-hop traversal
        ...
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_engine.py -k "transitive" -v`
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/mergeguard/models.py src/mergeguard/core/engine.py tests/unit/test_engine.py
git commit -m "fix: reduce transitive BFS depth from 5 to 1 (direct imports only)

Adds max_transitive_depth config (default 1). At depth 5, BFS reaches
the entire connected component in well-connected repos. Direct-import
conflicts at depth 1 are sufficient — deeper chains are already caught
by direct-dependency checks at each hop."
```

---

### Task 3: Require symbol-level evidence for transitive WARNING severity

Currently all transitive conflicts get `WARNING` regardless of whether the imported symbols overlap with the changed symbols. The code already computes this overlap in `_build_transitive_detail` but doesn't use it for severity decisions.

**Severity rules:**
- `imported_syms` non-empty (imported symbols overlap with changed symbols): `WARNING`
- `imported_syms` empty (no evidence of actual symbol interaction): `INFO`

**Files:**
- Modify: `src/mergeguard/core/engine.py` (Direction A and Direction B conflict creation)

- [ ] **Step 1: Add severity logic to Direction A**

In `src/mergeguard/core/engine.py`, in the Direction A conflict creation (around line 876), replace:

```python
                            severity=ConflictSeverity.WARNING,
```

With a conditional computed before the Conflict constructor:

```python
                    severity = ConflictSeverity.WARNING if imported_syms else ConflictSeverity.INFO

                    transitive.append(
                        Conflict(
                            ...
                            severity=severity,
                            ...
                        )
                    )
```

- [ ] **Step 2: Apply same logic to Direction B**

In Direction B (around line 932), replace:

```python
                            severity=ConflictSeverity.WARNING,
```

With:

```python
                    severity_b = ConflictSeverity.WARNING if imported_syms_b else ConflictSeverity.INFO
```

And use `severity=severity_b` in the Conflict constructor.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/test_engine.py -k "transitive" -v`

Tests that need severity assertion updates:
- `test_basic_transitive_detected` (line 394): graph edge `("src/views.py", "models")` has no imported names → becomes `INFO`
- `test_transitive_description_fallback_no_imported_names` (line 672): no imported names → becomes `INFO`
- `test_transitive_description_includes_imported_symbols` (line 635): has `["User"]` overlap → stays `WARNING`

Update the failing assertions accordingly.

- [ ] **Step 4: Add tests for the new severity behavior**

Add to the transitive test class:

```python
    def test_transitive_without_symbol_overlap_is_info(self):
        """When imported symbols don't overlap with changed symbols, severity is INFO."""
        engine = self._make_engine()
        target = _make_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="Admin",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_body",
                diff_lines=(1, 10),
            ),
        ]
        other = _make_pr(2, ["src/views.py"])

        # views.py imports User from models — but Admin changed, not User
        graph = self._make_graph([("src/views.py", "models", ["User"])])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].severity == ConflictSeverity.INFO

    def test_transitive_with_symbol_overlap_is_warning(self):
        """When imported symbols overlap with changed symbols, severity is WARNING."""
        engine = self._make_engine()
        target = _make_pr(1, ["src/models.py"])
        target.changed_symbols = [
            ChangedSymbol(
                symbol=Symbol(
                    name="User",
                    symbol_type=SymbolType.CLASS,
                    file_path="src/models.py",
                    start_line=1,
                    end_line=10,
                ),
                change_type="modified_signature",
                diff_lines=(1, 10),
            ),
        ]
        other = _make_pr(2, ["src/views.py"])

        # views.py imports User from models — and User changed
        graph = self._make_graph([("src/views.py", "models", ["User"])])

        with patch("mergeguard.core.engine.build_dependency_graph", return_value=graph):
            result = engine._detect_transitive_conflicts(target, [other], [])

        assert len(result) == 1
        assert result[0].severity == ConflictSeverity.WARNING
```

- [ ] **Step 5: Run all transitive tests**

Run: `uv run pytest tests/unit/test_engine.py -k "transitive" -v`
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/mergeguard/core/engine.py tests/unit/test_engine.py
git commit -m "fix: require symbol-level evidence for transitive WARNING severity

Transitive conflicts without imported-symbol overlap with changed
symbols are demoted to INFO. Only conflicts where the dependent file
imports specific symbols that were actually modified get WARNING."
```

---

### Task 5: Fix Windows encoding crash in benchmark runner

Three FastAPI PRs crashed with `'charmap' codec can't encode character` — PR titles with emojis crash on Windows console encoding.

**Files:**
- Modify: `benchmarks/run_benchmarks.py`

- [ ] **Step 1: Add UTF-8 encoding fix**

At the top of `benchmarks/run_benchmarks.py`, after the existing imports but before the `sys.path.insert` line, add:

```python
# Fix Windows console encoding for repos with emoji in PR titles
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
```

- [ ] **Step 2: Commit**

```bash
git add benchmarks/run_benchmarks.py
git commit -m "fix: handle emoji in PR titles on Windows console encoding"
```

---

## Final Verification

- [ ] **Run full lint suite**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

- [ ] **Run full test suite**

```bash
uv run pytest tests/ -q --deselect tests/unit/test_engine.py::TestCacheSymlinkRejection::test_symlink_cache_dir_raises
```

- [ ] **Commit any formatting fixes**

```bash
uv run ruff format src/ tests/
git add -u && git commit -m "style: format after transitive accuracy fixes"
```

---

## Expected Impact

Before these fixes (FastAPI benchmark):
- PR #15300: 46 conflicts (38 transitive)
- PR #15295: 109 conflicts (109 transitive)

After these fixes (predicted):
- PR #15300: ~8-10 conflicts (2 hard + 6 behavioral + 0-2 transitive with symbol evidence)
- PR #15295: ~0-3 conflicts (only transitive with direct import AND symbol overlap)

The three fixes compound:
1. **Fix 1** (trim module forms): Removes false dependents caused by ambiguous short names
2. **Fix 2** (depth=1): Limits to direct imports — deeper chains are already caught at each hop
3. **Fix 3** (symbol evidence): Demotes remaining noise to INFO, keeping only symbol-verified conflicts as WARNING
