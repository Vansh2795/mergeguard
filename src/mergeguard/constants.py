"""Shared constants and enums for MergeGuard."""

from __future__ import annotations

# GitHub API
GITHUB_API_BASE = "https://api.github.com"
GITHUB_DIFF_ACCEPT = "application/vnd.github.v3.diff"
GITHUB_JSON_ACCEPT = "application/vnd.github.v3+json"

# MergeGuard comment marker (used to identify/update existing comments)
COMMENT_MARKER = "<!-- mergeguard-report -->"

# Default config file name
DEFAULT_CONFIG_FILE = ".mergeguard.yml"

# Cache directory
CACHE_DIR = ".mergeguard-cache"

# Performance limits
DEFAULT_MAX_OPEN_PRS = 30
DEFAULT_MAX_FILE_SIZE = 500_000  # 500KB — skip very large files
DEFAULT_MAX_DIFF_SIZE = 100_000  # 100KB — truncate very large diffs

# Risk score thresholds
RISK_HIGH = 70
RISK_MEDIUM = 40
RISK_LOW = 0

# Risk score weights (must sum to 1.0)
DEFAULT_RISK_WEIGHTS = {
    "conflict_severity": 0.30,
    "blast_radius": 0.25,
    "pattern_deviation": 0.20,
    "churn_risk": 0.15,
    "ai_attribution": 0.10,
}

# Supported file extensions for AST parsing
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".rb", ".php", ".c", ".cpp", ".cs", ".swift", ".kt",
}

# File patterns to always ignore
DEFAULT_IGNORED_PATTERNS = [
    "*.lock",
    "*.min.js",
    "*.min.css",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
]
