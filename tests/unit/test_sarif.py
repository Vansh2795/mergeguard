"""Tests for SARIF output formatter."""

from __future__ import annotations

import json

from mergeguard.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
)
from mergeguard.output.sarif import RULE_IDS, format_sarif


class TestFormatSarif:
    def test_valid_json(self, sample_report):
        result = format_sarif(sample_report)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_sarif_structure(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        assert "$schema" in parsed
        assert parsed["version"] == "2.1.0"
        assert len(parsed["runs"]) == 1

    def test_tool_driver(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        driver = parsed["runs"][0]["tool"]["driver"]
        assert driver["name"] == "MergeGuard"
        assert "version" in driver

    def test_rule_ids_match_conflict_types(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        result_rule_ids = {r["ruleId"] for r in parsed["runs"][0]["results"]}
        driver_rule_ids = {r["id"] for r in parsed["runs"][0]["tool"]["driver"]["rules"]}
        # Every result rule must have a corresponding driver rule
        assert result_rule_ids <= driver_rule_ids

    def test_severity_critical_maps_to_error(self, sample_report):
        # sample_conflict has CRITICAL severity
        parsed = json.loads(format_sarif(sample_report))
        assert parsed["runs"][0]["results"][0]["level"] == "error"

    def test_severity_warning(self, sample_pr):
        from mergeguard.models import ConflictReport

        conflict = Conflict(
            conflict_type=ConflictType.BEHAVIORAL,
            severity=ConflictSeverity.WARNING,
            source_pr=42,
            target_pr=43,
            file_path="src/foo.py",
            description="Behavioral conflict",
            recommendation="Review carefully",
        )
        report = ConflictReport(pr=sample_pr, conflicts=[conflict])
        parsed = json.loads(format_sarif(report))
        assert parsed["runs"][0]["results"][0]["level"] == "warning"

    def test_severity_info(self, sample_pr):
        from mergeguard.models import ConflictReport

        conflict = Conflict(
            conflict_type=ConflictType.DUPLICATION,
            severity=ConflictSeverity.INFO,
            source_pr=42,
            target_pr=43,
            file_path="src/foo.py",
            description="Duplicate work",
            recommendation="Consider consolidating",
        )
        report = ConflictReport(pr=sample_pr, conflicts=[conflict])
        parsed = json.loads(format_sarif(report))
        assert parsed["runs"][0]["results"][0]["level"] == "note"

    def test_location_without_source_lines(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        loc = parsed["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "src/users/service.py"
        assert "region" not in loc

    def test_location_with_source_lines(self, sample_pr):
        from mergeguard.models import ConflictReport

        conflict = Conflict(
            conflict_type=ConflictType.HARD,
            severity=ConflictSeverity.CRITICAL,
            source_pr=42,
            target_pr=43,
            file_path="src/auth.py",
            description="Hard conflict",
            recommendation="Fix it",
            source_lines=(10, 20),
        )
        report = ConflictReport(pr=sample_pr, conflicts=[conflict])
        parsed = json.loads(format_sarif(report))
        region = parsed["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert region["startLine"] == 10
        assert region["endLine"] == 20

    def test_message_includes_target_pr(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        msg = parsed["runs"][0]["results"][0]["message"]["text"]
        assert "(conflicts with PR #43)" in msg

    def test_empty_report(self, empty_report):
        parsed = json.loads(format_sarif(empty_report))
        assert parsed["runs"][0]["results"] == []
        assert parsed["runs"][0]["tool"]["driver"]["rules"] == []

    def test_only_used_rules_included(self, sample_report):
        parsed = json.loads(format_sarif(sample_report))
        rules = parsed["runs"][0]["tool"]["driver"]["rules"]
        # sample_conflict is HARD type only
        assert len(rules) == 1
        assert rules[0]["id"] == "mergeguard/hard-conflict"

    def test_all_conflict_types_have_rule_ids(self):
        """Every ConflictType member must be mapped in RULE_IDS."""
        for ct in ConflictType:
            assert ct in RULE_IDS, f"Missing RULE_ID for {ct}"
