"""Tests for blast radius visualization — data building and output formats."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from mergeguard.analysis.dependency import DependencyGraph, ImportEdge
from mergeguard.models import (
    BlastRadiusData,
    ChangedFile,
    Conflict,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    PRInfo,
)
from mergeguard.output.blast_radius import (
    build_blast_radius_data,
    format_blast_radius_html,
    format_blast_radius_json,
    format_blast_radius_terminal,
)

# ── Helpers ──────────────────────────────────────────────────────────

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


def _make_pr(
    number: int,
    *,
    title: str | None = None,
    author: str = "alice",
    files: list[str] | None = None,
) -> PRInfo:
    return PRInfo(
        number=number,
        title=title or f"PR #{number}",
        author=author,
        base_branch="main",
        head_branch=f"feature-{number}",
        head_sha=f"sha{number}",
        created_at=_NOW,
        updated_at=_NOW,
        changed_files=[
            ChangedFile(path=f, status=FileChangeStatus.MODIFIED) for f in (files or [])
        ],
    )


def _make_conflict(
    source_pr: int,
    target_pr: int,
    *,
    severity: ConflictSeverity = ConflictSeverity.CRITICAL,
    conflict_type: ConflictType = ConflictType.HARD,
    file_path: str = "src/main.py",
    is_intra_stack: bool = False,
) -> Conflict:
    return Conflict(
        conflict_type=conflict_type,
        severity=severity,
        source_pr=source_pr,
        target_pr=target_pr,
        file_path=file_path,
        description="Test conflict",
        recommendation="Fix it",
        is_intra_stack=is_intra_stack,
    )


def _make_report(
    pr_number: int,
    conflicts: list[Conflict] | None = None,
    *,
    risk_score: float = 50.0,
    files: list[str] | None = None,
    stack_group: str | None = None,
    stack_pr_numbers: list[int] | None = None,
) -> ConflictReport:
    return ConflictReport(
        pr=_make_pr(pr_number, files=files),
        conflicts=conflicts or [],
        risk_score=risk_score,
        stack_group=stack_group,
        stack_pr_numbers=stack_pr_numbers or [],
    )


# ── Data building tests ─────────────────────────────────────────────


class TestBuildBlastRadiusData:
    def test_empty_reports(self):
        data = build_blast_radius_data([], "owner/repo")
        assert data.nodes == []
        assert data.edges == []
        assert data.repo == "owner/repo"

    def test_single_pr_no_conflicts(self):
        reports = [_make_report(42)]
        data = build_blast_radius_data(reports, "owner/repo")
        assert len(data.nodes) == 1
        assert data.nodes[0].pr_number == 42
        assert data.nodes[0].direct_blast == 0
        assert data.nodes[0].transitive_blast == 0
        assert data.nodes[0].severity_max == "none"
        assert data.edges == []

    def test_two_prs_mutual_conflicts(self):
        c1 = _make_conflict(42, 38, severity=ConflictSeverity.CRITICAL)
        c2 = _make_conflict(
            42,
            38,
            severity=ConflictSeverity.WARNING,
            conflict_type=ConflictType.BEHAVIORAL,
        )
        reports = [
            _make_report(42, [c1, c2], risk_score=78),
            _make_report(38, [], risk_score=45),
        ]
        data = build_blast_radius_data(reports, "owner/repo")

        assert len(data.nodes) == 2
        assert len(data.edges) == 1

        edge = data.edges[0]
        assert edge.source_pr == 38
        assert edge.target_pr == 42
        assert edge.conflict_count == 2
        assert edge.severity_max == "critical"

        # Node 42 should have direct_blast=1 (conflicts with 38)
        node42 = next(n for n in data.nodes if n.pr_number == 42)
        assert node42.direct_blast == 1
        assert node42.transitive_blast == 1

    def test_transitive_blast_radius(self):
        """A↔B, B↔C → A has transitive=2 (can reach B and C)."""
        c_ab = _make_conflict(1, 2)
        c_bc = _make_conflict(2, 3)
        reports = [
            _make_report(1, [c_ab]),
            _make_report(2, [c_bc]),
            _make_report(3, []),
        ]
        data = build_blast_radius_data(reports, "owner/repo")

        node1 = next(n for n in data.nodes if n.pr_number == 1)
        node3 = next(n for n in data.nodes if n.pr_number == 3)
        assert node1.transitive_blast == 2  # reaches 2 and 3
        assert node3.transitive_blast == 2  # reaches 2 and 1
        assert node1.direct_blast == 1  # only directly connected to 2

    def test_intra_stack_edge_flagging(self):
        c = _make_conflict(10, 11, is_intra_stack=True)
        reports = [
            _make_report(10, [c]),
            _make_report(11, []),
        ]
        data = build_blast_radius_data(reports, "owner/repo")
        assert data.edges[0].is_intra_stack is True

    def test_stack_group_attachment(self):
        reports = [
            _make_report(10, stack_group="chain-auth", stack_pr_numbers=[10, 11, 12]),
            _make_report(11, stack_group="chain-auth", stack_pr_numbers=[10, 11, 12]),
            _make_report(12, stack_group="chain-auth", stack_pr_numbers=[10, 11, 12]),
        ]
        data = build_blast_radius_data(reports, "owner/repo")
        assert len(data.stack_groups) == 1
        assert data.stack_groups[0]["group_id"] == "chain-auth"
        assert data.stack_groups[0]["pr_numbers"] == [10, 11, 12]

        node10 = next(n for n in data.nodes if n.pr_number == 10)
        assert node10.stack_group == "chain-auth"

    def test_file_graph_edges_extracted(self):
        graph = DependencyGraph()
        graph.add_edge(
            ImportEdge(
                source_file="src/a.py",
                target_file="src/b.py",
                imported_names=["Foo"],
            )
        )
        graph.add_edge(
            ImportEdge(
                source_file="src/c.py",
                target_file="src/d.py",
                imported_names=["Bar"],
            )
        )

        reports = [
            _make_report(1, files=["src/a.py", "src/b.py"]),
            _make_report(2, files=["src/c.py"]),
        ]
        data = build_blast_radius_data(reports, "owner/repo", file_graph=graph)
        # Both edges should be included (a.py, b.py are changed; c.py is changed)
        assert len(data.file_edges) == 2
        assert data.file_edges[0]["source"] == "src/a.py"
        assert data.file_edges[0]["symbols"] == ["Foo"]

    def test_severity_max_computed_correctly(self):
        """critical > warning > info."""
        c1 = _make_conflict(1, 2, severity=ConflictSeverity.INFO)
        c2 = _make_conflict(1, 2, severity=ConflictSeverity.WARNING)
        reports = [_make_report(1, [c1, c2]), _make_report(2, [])]
        data = build_blast_radius_data(reports, "owner/repo")
        edge = data.edges[0]
        assert edge.severity_max == "warning"

        node1 = next(n for n in data.nodes if n.pr_number == 1)
        assert node1.severity_max == "warning"

    def test_conflict_types_aggregated(self):
        c1 = _make_conflict(1, 2, conflict_type=ConflictType.HARD)
        c2 = _make_conflict(1, 2, conflict_type=ConflictType.BEHAVIORAL)
        c3 = _make_conflict(1, 2, conflict_type=ConflictType.HARD)  # Duplicate type
        reports = [_make_report(1, [c1, c2, c3]), _make_report(2, [])]
        data = build_blast_radius_data(reports, "owner/repo")
        edge = data.edges[0]
        assert sorted(edge.conflict_types) == ["behavioral", "hard"]

    def test_bidirectional_edge_deduplication(self):
        """A→B and B→A should result in one edge, not two."""
        c1 = _make_conflict(1, 2)
        c2 = _make_conflict(2, 1)
        reports = [_make_report(1, [c1]), _make_report(2, [c2])]
        data = build_blast_radius_data(reports, "owner/repo")
        assert len(data.edges) == 1
        assert data.edges[0].conflict_count == 2


# ── Terminal output tests ────────────────────────────────────────────


class TestTerminalOutput:
    def test_renders_without_error(self, capsys):
        c = _make_conflict(1, 2)
        reports = [_make_report(1, [c], risk_score=75), _make_report(2, [], risk_score=30)]
        data = build_blast_radius_data(reports, "owner/repo")
        # Should not raise
        format_blast_radius_terminal(data)

    def test_sorted_by_transitive_blast(self):
        c_ab = _make_conflict(1, 2)
        c_bc = _make_conflict(2, 3)
        reports = [
            _make_report(1, [c_ab]),
            _make_report(2, [c_bc]),
            _make_report(3, []),
        ]
        data = build_blast_radius_data(reports, "owner/repo")
        sorted_nodes = sorted(data.nodes, key=lambda n: n.transitive_blast, reverse=True)
        # All three should have transitive_blast=2 since they're all connected
        assert all(n.transitive_blast == 2 for n in sorted_nodes)


# ── JSON output tests ────────────────────────────────────────────────


class TestJsonOutput:
    def test_valid_json(self):
        c = _make_conflict(1, 2)
        reports = [_make_report(1, [c]), _make_report(2, [])]
        data = build_blast_radius_data(reports, "owner/repo")
        result = format_blast_radius_json(data)
        parsed = json.loads(result)
        assert parsed["repo"] == "owner/repo"
        assert len(parsed["nodes"]) == 2
        assert len(parsed["edges"]) == 1

    def test_round_trip(self):
        c = _make_conflict(1, 2, severity=ConflictSeverity.WARNING)
        reports = [_make_report(1, [c]), _make_report(2, [])]
        data = build_blast_radius_data(reports, "owner/repo")
        result = format_blast_radius_json(data)
        roundtripped = BlastRadiusData.model_validate_json(result)
        assert roundtripped.repo == data.repo
        assert len(roundtripped.nodes) == len(data.nodes)
        assert len(roundtripped.edges) == len(data.edges)


# ── HTML output tests ────────────────────────────────────────────────


class TestHtmlOutput:
    def test_contains_d3_script(self):
        data = build_blast_radius_data([], "owner/repo")
        html = format_blast_radius_html(data)
        assert "d3.v7.min.js" in html

    def test_contains_embedded_json(self):
        c = _make_conflict(1, 2)
        reports = [_make_report(1, [c]), _make_report(2, [])]
        data = build_blast_radius_data(reports, "owner/repo")
        html = format_blast_radius_html(data)
        assert "const DATA =" in html
        assert '"pr_number"' in html

    def test_contains_graph_svg(self):
        data = build_blast_radius_data([], "owner/repo")
        html = format_blast_radius_html(data)
        assert '<svg id="graph">' in html

    def test_contains_legend_and_controls(self):
        data = build_blast_radius_data([], "owner/repo")
        html = format_blast_radius_html(data)
        assert "Legend" in html
        assert 'id="resetBtn"' in html
        assert 'id="severityFilter"' in html
        assert 'id="searchPR"' in html

    def test_repo_in_title(self):
        data = build_blast_radius_data([], "acme/widget")
        html = format_blast_radius_html(data)
        assert "acme/widget" in html


# ── Engine integration tests ─────────────────────────────────────────


class TestEngineIntegration:
    def test_build_file_dependency_graph_empty(self):
        """build_file_dependency_graph with empty list returns empty graph."""
        from unittest.mock import MagicMock

        from mergeguard.core.engine import MergeGuardEngine

        engine = MergeGuardEngine.__new__(MergeGuardEngine)
        engine._config = MagicMock()
        result = engine.build_file_dependency_graph([])
        assert isinstance(result, DependencyGraph)
        assert result.edges == []
