"""Tests for the CODEOWNERS parser (analysis/codeowners.py)."""

from __future__ import annotations

from mergeguard.analysis.codeowners import (
    CodeOwnerRule,
    CodeOwners,
    _pattern_matches,
    load_codeowners,
)

# ──────────────────────────────────────────────
# Pattern matching
# ──────────────────────────────────────────────


class TestPatternMatches:
    """Test the low-level _pattern_matches() helper."""

    def test_star_matches_everything(self):
        assert _pattern_matches("*", "src/foo.py")
        assert _pattern_matches("*", "README.md")

    def test_extension_glob(self):
        assert _pattern_matches("*.py", "src/utils/helper.py")
        assert _pattern_matches("*.py", "main.py")
        assert not _pattern_matches("*.py", "src/utils/helper.js")

    def test_directory_glob(self):
        assert _pattern_matches("src/**", "src/foo.py")
        assert _pattern_matches("src/**", "src/deep/nested/file.py")
        assert not _pattern_matches("src/**", "lib/foo.py")

    def test_specific_file(self):
        # Without a slash, pattern matches at any depth (CODEOWNERS spec)
        assert _pattern_matches("Makefile", "Makefile")
        assert _pattern_matches("Makefile", "src/Makefile")

    def test_anchored_pattern(self):
        assert _pattern_matches("/docs/*", "docs/guide.md")
        assert not _pattern_matches("/docs/*", "src/docs/guide.md")

    def test_trailing_slash_directory(self):
        assert _pattern_matches("docs/", "docs/guide.md")
        assert _pattern_matches("docs/", "docs/sub/file.md")

    def test_nested_directory_pattern(self):
        assert _pattern_matches("src/components/*", "src/components/Button.tsx")
        # In CODEOWNERS, * in a path does match subdirs via fnmatch
        assert _pattern_matches("src/components/*", "src/components/sub/Button.tsx")

    def test_wildcard_in_directory(self):
        assert _pattern_matches("*.js", "src/app.js")
        assert _pattern_matches("*.js", "app.js")


# ──────────────────────────────────────────────
# GitHub format parsing
# ──────────────────────────────────────────────


class TestGitHubFormat:
    """Test GitHub CODEOWNERS format parsing."""

    GITHUB_CONTENT = """\
# This is a comment
* @global-team

# Frontend
*.js @frontend-team
*.tsx @frontend-team
src/components/** @frontend-team @ui-lead

# Backend
src/api/** @backend-team
src/models/** @backend-team @db-team

# Docs
docs/* @docs-team
"""

    def test_parse_basic(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        assert len(co.rules) > 0
        assert all(isinstance(r, CodeOwnerRule) for r in co.rules)

    def test_skip_comments(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        for rule in co.rules:
            assert not rule.pattern.startswith("#")

    def test_star_default_owner(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        assert co.rules[0].pattern == "*"
        assert co.rules[0].owners == ["@global-team"]

    def test_last_match_wins(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        # src/components/Button.tsx matches both *.tsx and src/components/**
        owners = co.resolve_owners("src/components/Button.tsx")
        assert "@frontend-team" in owners
        assert "@ui-lead" in owners

    def test_fallback_to_default(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        owners = co.resolve_owners("random_file.txt")
        assert owners == ["@global-team"]

    def test_extension_match(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        owners = co.resolve_owners("lib/utils.js")
        assert "@frontend-team" in owners

    def test_directory_match(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        owners = co.resolve_owners("src/api/routes.py")
        assert "@backend-team" in owners

    def test_multiple_owners(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        owners = co.resolve_owners("src/models/user.py")
        assert "@backend-team" in owners
        assert "@db-team" in owners

    def test_resolve_owners_for_files(self):
        co = CodeOwners(self.GITHUB_CONTENT)
        result = co.resolve_owners_for_files(["src/api/routes.py", "docs/guide.md"])
        assert "@backend-team" in result["src/api/routes.py"]
        assert "@docs-team" in result["docs/guide.md"]


# ──────────────────────────────────────────────
# GitLab format parsing
# ──────────────────────────────────────────────


class TestGitLabFormat:
    """Test GitLab CODEOWNERS format with section headers."""

    GITLAB_CONTENT = """\
# Global default
* @global-owner

[Frontend]
*.js @frontend-team
*.css @frontend-team
src/components/** @ui-team

[Backend]
src/api/** @backend-team
src/models/** @data-team

[DevOps]
Dockerfile @devops-team
docker-compose.yml @devops-team
.github/** @devops-team
"""

    def test_parse_sections(self):
        co = CodeOwners(self.GITLAB_CONTENT, gitlab=True)
        sections = {r.section for r in co.rules}
        assert None in sections  # global
        assert "Frontend" in sections
        assert "Backend" in sections
        assert "DevOps" in sections

    def test_section_scoped_rules(self):
        co = CodeOwners(self.GITLAB_CONTENT, gitlab=True)
        frontend_rules = [r for r in co.rules if r.section == "Frontend"]
        assert len(frontend_rules) == 3

    def test_resolve_still_last_match_wins(self):
        co = CodeOwners(self.GITLAB_CONTENT, gitlab=True)
        owners = co.resolve_owners("src/components/Button.js")
        # *.js matches first, then src/components/** overwrites
        assert "@ui-team" in owners

    def test_optional_section_header_syntax(self):
        content = "^[Optional Section]\n*.md @docs-team\n"
        co = CodeOwners(content, gitlab=True)
        assert co.rules[0].section == "Optional Section"
        assert co.rules[0].owners == ["@docs-team"]

    def test_section_header_with_default_owners(self):
        content = "[Security] @security-team\nsrc/auth/** @auth-team\n"
        co = CodeOwners(content, gitlab=True)
        assert co.rules[0].pattern == "*"
        assert co.rules[0].section == "Security"
        assert co.rules[0].owners == ["@security-team"]


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and graceful handling."""

    def test_empty_content(self):
        co = CodeOwners("")
        assert co.rules == []
        assert co.resolve_owners("anything.py") == []

    def test_comments_only(self):
        co = CodeOwners("# just comments\n# nothing else\n")
        assert co.rules == []

    def test_lines_without_owners(self):
        co = CodeOwners("pattern_without_owner\n")
        assert co.rules == []

    def test_no_matching_pattern(self):
        co = CodeOwners("src/** @team-a\n")
        # File outside src/ with no default * rule
        owners = co.resolve_owners("lib/utils.py")
        assert owners == []

    def test_load_codeowners_no_file(self):
        """load_codeowners returns None when no CODEOWNERS exists."""

        class FakeClient:
            def get_file_content(self, path: str, ref: str) -> str | None:
                return None

        result = load_codeowners(FakeClient(), "owner/repo")  # type: ignore[arg-type]
        assert result is None

    def test_load_codeowners_finds_file(self):
        """load_codeowners finds CODEOWNERS and parses it."""

        class FakeClient:
            def get_file_content(self, path: str, ref: str) -> str | None:
                if path == ".github/CODEOWNERS":
                    return "* @default-team\n"
                return None

        result = load_codeowners(FakeClient(), "owner/repo")  # type: ignore[arg-type]
        assert result is not None
        assert result.resolve_owners("anything") == ["@default-team"]

    def test_load_codeowners_gitlab_autodetect(self):
        """load_codeowners auto-detects GitLab format from section headers."""

        class FakeClient:
            def get_file_content(self, path: str, ref: str) -> str | None:
                if path == "CODEOWNERS":
                    return "[Frontend]\n*.js @fe-team\n"
                return None

        result = load_codeowners(FakeClient(), "owner/repo")  # type: ignore[arg-type]
        assert result is not None
        assert result.rules[0].section == "Frontend"

    def test_load_codeowners_tries_all_paths(self):
        """load_codeowners checks docs/CODEOWNERS as last resort."""

        class FakeClient:
            def get_file_content(self, path: str, ref: str) -> str | None:
                if path == "docs/CODEOWNERS":
                    return "*.md @docs-team\n"
                return None

        result = load_codeowners(FakeClient(), "owner/repo")  # type: ignore[arg-type]
        assert result is not None
