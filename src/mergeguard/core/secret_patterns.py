"""Builtin secret detection patterns for PR diff scanning."""

from __future__ import annotations

from mergeguard.models import ConflictSeverity, SecretPattern

BUILTIN_PATTERNS: list[SecretPattern] = [
    SecretPattern(
        name="AWS Access Key",
        pattern=r"AKIA[0-9A-Z]{16}",
    ),
    SecretPattern(
        name="AWS Secret Key",
        pattern=r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}",
    ),
    SecretPattern(
        name="GitHub PAT",
        pattern=r"ghp_[A-Za-z0-9]{36}",
    ),
    SecretPattern(
        name="GitHub OAuth",
        pattern=r"gho_[A-Za-z0-9]{36}",
    ),
    SecretPattern(
        name="GitHub App Token",
        pattern=r"gh[usr]_[A-Za-z0-9]{36}",
    ),
    SecretPattern(
        name="GitLab PAT",
        pattern=r"glpat-[A-Za-z0-9_\-]{20}",
    ),
    SecretPattern(
        name="Slack Token",
        pattern=r"xox[baprs]-[0-9a-zA-Z\-]{10,}",
    ),
    SecretPattern(
        name="Slack Webhook",
        pattern=r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+",
    ),
    SecretPattern(
        name="Generic API Key",
        pattern=r"(?i)(api[_\-]?key|api[_\-]?secret)\s*[:=]\s*['\"][A-Za-z0-9]{20,}['\"]",
    ),
    SecretPattern(
        name="Generic Secret",
        pattern=r"(?i)(secret|password|passwd|pwd|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
    ),
    SecretPattern(
        name="Private Key",
        pattern=r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
    ),
    SecretPattern(
        name="Heroku API Key",
        pattern=r"[hH][eE][rR][oO][kK][uU].*[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
    ),
    SecretPattern(
        name="Stripe Key",
        pattern=r"[sr]k_(live|test)_[0-9a-zA-Z]{24,}",
    ),
    SecretPattern(
        name="Twilio API Key",
        pattern=r"SK[0-9a-fA-F]{32}",
    ),
    SecretPattern(
        name="SendGrid API Key",
        pattern=r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}",
        severity=ConflictSeverity.CRITICAL,
    ),
]
