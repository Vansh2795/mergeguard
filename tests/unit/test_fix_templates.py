"""Tests for template-based fix suggestion generators."""

from __future__ import annotations

from mergeguard.core.fix_templates import generate_template_suggestion
from mergeguard.models import Conflict, ConflictSeverity, ConflictType


def _make_conflict(
    conflict_type: ConflictType,
    symbol_name: str | None = "process_data",
    file_path: str = "src/service.py",
    source_pr: int = 42,
    target_pr: int = 43,
) -> Conflict:
    return Conflict(
        conflict_type=conflict_type,
        severity=ConflictSeverity.WARNING,
        source_pr=source_pr,
        target_pr=target_pr,
        file_path=file_path,
        symbol_name=symbol_name,
        description="Test conflict",
        recommendation="Test recommendation",
    )


class TestHardConflict:
    def test_with_symbol(self):
        result = generate_template_suggestion(_make_conflict(ConflictType.HARD))
        assert result is not None
        assert "#43" in result
        assert "process_data" in result
        assert "Rebase" in result

    def test_without_symbol(self):
        result = generate_template_suggestion(_make_conflict(ConflictType.HARD, symbol_name=None))
        assert result is not None
        assert "overlapping lines" in result.lower() or "merge markers" in result.lower()


class TestBehavioralConflict:
    def test_caller_callee_relationship(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.BEHAVIORAL, symbol_name="caller→callee")
        )
        assert result is not None
        assert "caller/callee" in result
        assert "end-to-end" in result.lower()

    def test_same_symbol_modification(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.BEHAVIORAL, symbol_name="update_user")
        )
        assert result is not None
        assert "update_user" in result
        assert "integration tests" in result.lower()


class TestInterfaceConflict:
    def test_signature_change(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.INTERFACE, symbol_name="get_user")
        )
        assert result is not None
        assert "old signature" in result.lower()
        assert "get_user" in result
        assert "#43" in result


class TestDuplicationConflict:
    def test_with_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.DUPLICATION, symbol_name="validate_input")
        )
        assert result is not None
        assert "validate_input" in result
        assert "reuse" in result.lower()

    def test_without_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.DUPLICATION, symbol_name=None)
        )
        assert result is not None
        assert "same problem" in result.lower()


class TestTransitiveConflict:
    def test_without_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.TRANSITIVE, symbol_name=None)
        )
        assert result is not None
        assert "depend" in result.lower()
        assert "#43" in result

    def test_with_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.TRANSITIVE, symbol_name="db_connect")
        )
        assert result is not None
        assert "db_connect" in result


class TestRegressionConflict:
    def test_with_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.REGRESSION, symbol_name="auth_handler")
        )
        assert result is not None
        assert "revert" in result.lower()
        assert "auth_handler" in result
        assert "intentional" in result.lower()

    def test_without_symbol(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.REGRESSION, symbol_name=None)
        )
        assert result is not None
        assert "revert" in result.lower()
        assert "intentional" in result.lower()


class TestSecretConflict:
    def test_secret_detection(self):
        result = generate_template_suggestion(
            _make_conflict(
                ConflictType.SECRET,
                file_path=".env",
                symbol_name=None,
            )
        )
        assert result is not None
        assert "rotate" in result.lower()
        assert ".env" in result
        assert "secrets manager" in result.lower() or "environment variables" in result.lower()


class TestGuardrailConflict:
    def test_guardrail_violation(self):
        result = generate_template_suggestion(
            _make_conflict(ConflictType.GUARDRAIL, symbol_name=None)
        )
        assert result is not None
        assert "guardrail" in result.lower()
        assert "src/service.py" in result


class TestGenerateTemplateSuggestion:
    def test_all_conflict_types_have_generators(self):
        """Every ConflictType should produce a non-None suggestion."""
        for ct in ConflictType:
            conflict = _make_conflict(ct)
            result = generate_template_suggestion(conflict)
            assert result is not None, f"No generator for {ct}"
            assert len(result) > 10, f"Suggestion too short for {ct}"

    def test_returns_string(self):
        result = generate_template_suggestion(_make_conflict(ConflictType.HARD))
        assert isinstance(result, str)
