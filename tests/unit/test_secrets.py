"""Tests for secret scanning in PR diffs."""

from __future__ import annotations

from datetime import datetime

from mergeguard.core.secrets import scan_secrets
from mergeguard.models import (
    ChangedFile,
    ConflictSeverity,
    ConflictType,
    FileChangeStatus,
    MergeGuardConfig,
    PRInfo,
    SecretPattern,
)


def _make_pr(patch: str, path: str = "config.py") -> PRInfo:
    """Create a minimal PRInfo with a single changed file."""
    return PRInfo(
        number=1,
        title="Test PR",
        author="test",
        base_branch="main",
        head_branch="feature",
        head_sha="abc123",
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
        changed_files=[
            ChangedFile(
                path=path,
                status=FileChangeStatus.MODIFIED,
                additions=1,
                patch=patch,
            )
        ],
    )


def _make_config(**kwargs) -> MergeGuardConfig:
    return MergeGuardConfig(**kwargs)


class TestSecretDetection:
    def test_detects_aws_access_key(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAI44QH8DHBR9MPVQZ'\n context")
        conflicts = scan_secrets(pr, _make_config())
        assert len(conflicts) >= 1
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 1
        assert aws[0].conflict_type == ConflictType.SECRET
        assert aws[0].severity == ConflictSeverity.CRITICAL

    def test_detects_github_pat(self):
        token = "ghp_" + "A" * 36
        pr = _make_pr(f"@@ -1,2 +1,3 @@\n context\n+TOKEN = '{token}'\n context")
        conflicts = scan_secrets(pr, _make_config())
        pat = [c for c in conflicts if c.symbol_name == "GitHub PAT"]
        assert len(pat) == 1

    def test_detects_private_key_header(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+-----BEGIN RSA PRIVATE KEY-----\n context")
        conflicts = scan_secrets(pr, _make_config())
        pk = [c for c in conflicts if c.symbol_name == "Private Key"]
        assert len(pk) == 1

    def test_detects_generic_password(self):
        pr = _make_pr('@@ -1,2 +1,3 @@\n context\n+password = "hunter2abc"\n context')
        conflicts = scan_secrets(pr, _make_config())
        generic = [c for c in conflicts if c.symbol_name == "Generic Secret"]
        assert len(generic) == 1

    def test_ignores_removed_lines(self):
        pr = _make_pr("@@ -1,3 +1,2 @@\n context\n-AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n context")
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 0

    def test_ignores_context_lines(self):
        pr = _make_pr(
            "@@ -1,3 +1,3 @@\n AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n+# new comment\n context"
        )
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 0

    def test_allowlist_suppresses_match(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n context")
        cfg = _make_config()
        cfg.secrets.allowlist = [r"EXAMPLE"]
        conflicts = scan_secrets(pr, cfg)
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 0

    def test_custom_pattern_from_config(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+MY_CUSTOM_KEY_abc123xyz\n context")
        cfg = _make_config()
        cfg.secrets.patterns = [
            SecretPattern(
                name="Custom Key",
                pattern=r"MY_CUSTOM_KEY_[a-z0-9]+",
            )
        ]
        conflicts = scan_secrets(pr, cfg)
        custom = [c for c in conflicts if c.symbol_name == "Custom Key"]
        assert len(custom) == 1

    def test_disabled_returns_empty(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n context")
        cfg = _make_config()
        cfg.secrets.enabled = False
        conflicts = scan_secrets(pr, cfg)
        assert conflicts == []

    def test_builtin_patterns_disabled(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n context")
        cfg = _make_config()
        cfg.secrets.use_builtin_patterns = False
        cfg.secrets.patterns = [
            SecretPattern(name="Custom", pattern=r"CUSTOM_[0-9]+"),
        ]
        conflicts = scan_secrets(pr, cfg)
        # No AWS key detected since builtins are off
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 0

    def test_redacts_secret_in_description(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAI44QH8DHBR9MPVQZ'\n context")
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 1
        # Full secret should not appear in description
        assert "AKIAI44QH8DHBR9MPVQZ" not in aws[0].description
        # Redacted form should appear
        assert "AKIA" in aws[0].description
        assert "..." in aws[0].description

    def test_source_lines_populated(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAI44QH8DHBR9MPVQZ'\n context")
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 1
        assert aws[0].source_lines is not None
        assert aws[0].source_lines[0] == aws[0].source_lines[1]  # Single line
        assert aws[0].source_lines[0] > 0

    def test_severity_from_pattern(self):
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+WARN_KEY_12345678901234567890\n context")
        cfg = _make_config()
        cfg.secrets.patterns = [
            SecretPattern(
                name="Warning Key",
                pattern=r"WARN_KEY_[0-9]{20,}",
                severity=ConflictSeverity.WARNING,
            )
        ]
        conflicts = scan_secrets(pr, cfg)
        warn = [c for c in conflicts if c.symbol_name == "Warning Key"]
        assert len(warn) == 1
        assert warn[0].severity == ConflictSeverity.WARNING

    def test_deduplicates_per_line(self):
        # Same pattern could match twice on one line, but we deduplicate by (file, line, pattern)
        pr = _make_pr(
            "@@ -1,2 +1,3 @@\n context\n+AKIAI44QH8DHBR9MPVQZ AKIAJ5WLQMVTZ3RNHK7A\n context"
        )
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 1  # Deduplicated: one finding per (file, line, pattern)

    def test_ignored_paths_skips_test_files(self):
        pr = _make_pr(
            "@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAI44QH8DHBR9MPVQZ'\n context",
            path="tests/unit/test_secrets.py",
        )
        conflicts = scan_secrets(pr, _make_config())
        assert len(conflicts) == 0

    def test_generic_secret_no_match_on_labels(self):
        # Enum values like `SECRET: "Secret Detected"` should not trigger
        pr = _make_pr(
            '@@ -1,2 +1,3 @@\n context\n+ConflictType.SECRET: "Secret Detected"\n context'
        )
        conflicts = scan_secrets(pr, _make_config())
        generic = [c for c in conflicts if c.symbol_name == "Generic Secret"]
        assert len(generic) == 0

    def test_builtin_allowlist_suppresses_example_keys(self):
        # AWS's documented example key (AKIAIOSFODNN7EXAMPLE) should be allowlisted
        pr = _make_pr("@@ -1,2 +1,3 @@\n context\n+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n context")
        conflicts = scan_secrets(pr, _make_config())
        aws = [c for c in conflicts if c.symbol_name == "AWS Access Key"]
        assert len(aws) == 0
