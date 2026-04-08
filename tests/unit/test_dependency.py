"""Tests for dependency graph building and depth computation."""

from __future__ import annotations

from mergeguard.analysis.dependency import (
    DependencyGraph,
    ImportEdge,
    build_dependency_graph,
    extract_imports,
    extract_imports_with_names,
)


class TestBuildDependencyGraph:
    def test_python_imports(self):
        """build_dependency_graph extracts Python imports and builds edges."""
        source = "from utils import helper\nimport os\nfrom models import User\n"
        graph = build_dependency_graph([("app.py", source)])
        assert len(graph.edges) == 3
        targets = {e.target_file for e in graph.edges}
        assert targets == {"utils", "os", "models"}
        assert all(e.source_file == "app.py" for e in graph.edges)

    def test_multiple_files(self):
        """Graph is built from multiple files."""
        files = [
            ("a.py", "import b\n"),
            ("b.py", "import c\n"),
            ("c.py", ""),
        ]
        graph = build_dependency_graph(files)
        assert len(graph.edges) == 2

    def test_empty_inputs(self):
        """Empty file list produces an empty graph."""
        graph = build_dependency_graph([])
        assert len(graph.edges) == 0

    def test_no_imports(self):
        """Files with no imports produce an empty graph."""
        graph = build_dependency_graph([("main.py", "x = 1\n")])
        assert len(graph.edges) == 0

    def test_js_imports(self):
        """build_dependency_graph handles JavaScript imports."""
        source = (
            "import React from 'react';\n"
            "import { useState } from 'react';\n"
            "import axios from 'axios';\n"
        )
        graph = build_dependency_graph([("app.tsx", source)])
        assert len(graph.edges) == 2
        targets = {e.target_file for e in graph.edges}
        assert targets == {"react", "axios"}
        react_edge = [e for e in graph.edges if e.target_file == "react"][0]
        assert react_edge.imported_names == ["useState"]


class TestDependencyDepth:
    def test_linear_chain(self):
        """a → b → c: depth of c should be 2 (a and b depend on it)."""
        graph = DependencyGraph()
        graph.add_edge(ImportEdge(source_file="a", target_file="b"))
        graph.add_edge(ImportEdge(source_file="b", target_file="c"))
        # c is imported by b, which is imported by a → 2 dependents
        assert graph.dependency_depth("c") == 2

    def test_no_dependents(self):
        """A file with no reverse dependencies has depth 0."""
        graph = DependencyGraph()
        graph.add_edge(ImportEdge(source_file="a", target_file="b"))
        assert graph.dependency_depth("a") == 0

    def test_empty_graph(self):
        """Depth of any file in an empty graph is 0."""
        graph = DependencyGraph()
        assert graph.dependency_depth("x") == 0

    def test_fan_in(self):
        """Multiple files importing the same target: depth is 1 (not fan-out count)."""
        graph = DependencyGraph()
        graph.add_edge(ImportEdge(source_file="a", target_file="shared"))
        graph.add_edge(ImportEdge(source_file="b", target_file="shared"))
        graph.add_edge(ImportEdge(source_file="c", target_file="shared"))
        assert graph.dependency_depth("shared") == 1

    def test_deep_chain(self):
        """A→B→C→D: depth(D) = 3."""
        graph = DependencyGraph()
        graph.add_edge(ImportEdge(source_file="a", target_file="b"))
        graph.add_edge(ImportEdge(source_file="b", target_file="c"))
        graph.add_edge(ImportEdge(source_file="c", target_file="d"))
        assert graph.dependency_depth("d") == 3


class TestImportedNames:
    """Tests for imported name extraction."""

    def test_python_from_import_names(self):
        """from X import Y, Z populates imported_names."""
        source = "from models import User, process_data\n"
        result = extract_imports_with_names(source, "app.py")
        assert len(result) == 1
        assert result[0] == ("models", ["User", "process_data"])

    def test_python_bare_import_no_names(self):
        """import X has empty imported_names."""
        source = "import models\n"
        result = extract_imports_with_names(source, "app.py")
        assert len(result) == 1
        assert result[0] == ("models", [])

    def test_python_import_with_alias(self):
        """from X import Y as Z extracts original name Y."""
        source = "from models import User as U\n"
        result = extract_imports_with_names(source, "app.py")
        assert len(result) == 1
        assert result[0] == ("models", ["User"])

    def test_js_named_import_names(self):
        """import { Y, Z } from 'X' populates imported_names."""
        source = "import { User, getData } from './models';\n"
        result = extract_imports_with_names(source, "app.tsx")
        assert len(result) == 1
        assert result[0] == ("./models", ["User", "getData"])

    def test_js_default_import_no_names(self):
        """import X from 'Y' has empty imported_names."""
        source = "import React from 'react';\n"
        result = extract_imports_with_names(source, "app.tsx")
        assert len(result) == 1
        assert result[0] == ("react", [])

    def test_build_graph_populates_imported_names(self):
        """build_dependency_graph passes imported names through to edges."""
        source = "from models import User, process_data\nimport os\n"
        graph = build_dependency_graph([("app.py", source)])
        assert len(graph.edges) == 2
        models_edge = [e for e in graph.edges if e.target_file == "models"][0]
        assert models_edge.imported_names == ["User", "process_data"]
        os_edge = [e for e in graph.edges if e.target_file == "os"][0]
        assert os_edge.imported_names == []

    def test_get_imported_names_lookup(self):
        """DependencyGraph.get_imported_names returns correct names."""
        graph = DependencyGraph()
        graph.add_edge(
            ImportEdge(
                source_file="views.py",
                target_file="models",
                imported_names=["User", "Admin"],
            )
        )
        assert graph.get_imported_names("views.py", "models") == ["User", "Admin"]
        assert graph.get_imported_names("views.py", "other") == []
        assert graph.get_imported_names("other.py", "models") == []

    def test_extract_imports_backward_compat(self):
        """extract_imports still returns list[str] without names."""
        source = "from models import User\nimport os\n"
        result = extract_imports(source, "app.py")
        assert result == ["models", "os"]


class TestGoImportScoping:
    def test_import_block_detected(self):
        from mergeguard.analysis.dependency import _extract_go_imports

        code = (
            'package main\n\nimport (\n    "fmt"\n    "os"\n)\n\n'
            'func main() {\n    msg := "hello/world"\n}\n'
        )
        imports = _extract_go_imports(code)
        assert "fmt" in imports
        assert "os" in imports

    def test_string_literal_not_detected_as_import(self):
        from mergeguard.analysis.dependency import _extract_go_imports

        code = (
            'package main\n\nimport "fmt"\n\nfunc main() {\n'
            '    msg := "net/http"\n    fmt.Println(msg)\n}\n'
        )
        imports = _extract_go_imports(code)
        assert "fmt" in imports
        assert "net/http" not in imports

    def test_single_import(self):
        from mergeguard.analysis.dependency import _extract_go_imports

        code = 'package main\n\nimport "fmt"\n'
        imports = _extract_go_imports(code)
        assert imports == ["fmt"]


class TestMultiLinePythonImports:
    def test_multiline_from_import_captures_names(self):
        from mergeguard.analysis.dependency import _extract_python_imports

        code = (
            "from mergeguard.models import (\n    PRInfo,\n    Conflict,\n    ConflictReport,\n)\n"
        )
        imports = _extract_python_imports(code)
        module_imports = {mod: names for mod, names in imports}
        assert "mergeguard.models" in module_imports
        names = module_imports["mergeguard.models"]
        assert "PRInfo" in names
        assert "Conflict" in names
        assert "ConflictReport" in names

    def test_single_line_still_works(self):
        from mergeguard.analysis.dependency import _extract_python_imports

        code = "from os.path import join, exists\n"
        imports = _extract_python_imports(code)
        module_imports = {mod: names for mod, names in imports}
        assert "join" in module_imports["os.path"]
        assert "exists" in module_imports["os.path"]

    def test_multiline_with_aliases(self):
        from mergeguard.analysis.dependency import _extract_python_imports

        code = "from typing import (\n    Optional as Opt,\n    List,\n)\n"
        imports = _extract_python_imports(code)
        module_imports = {mod: names for mod, names in imports}
        names = module_imports["typing"]
        assert "Optional" in names
        assert "List" in names
