# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.5.x   | :white_check_mark: |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in MergeGuard, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Email **security@mergeguard.dev** with a description of the vulnerability
2. Include steps to reproduce, if possible
3. Include the version of MergeGuard affected

### What to Expect

- **Acknowledgment**: Within 48 hours of your report
- **Assessment**: Within 5 business days, we will assess the severity and impact
- **Resolution**: We aim to release a fix within 14 days of confirming the vulnerability
- **Disclosure**: We will coordinate public disclosure with you after the fix is released

### Scope

The following are in scope for security reports:

- **Token/credential exposure**: Any path where GitHub/GitLab tokens, API keys, or other credentials could be leaked (logs, error messages, cache files, reports)
- **Code injection**: Vulnerabilities in diff parsing, AST analysis, or config loading that could execute arbitrary code
- **Path traversal**: File access outside intended directories via crafted PR data
- **Dependency vulnerabilities**: Critical CVEs in direct dependencies

### Out of Scope

- Denial of service via large repositories (this is a known limitation)
- Issues requiring physical access to the machine running MergeGuard
- Social engineering attacks
- Vulnerabilities in third-party services (GitHub, GitLab APIs)

## Security Best Practices

When using MergeGuard:

- **Tokens**: Use fine-grained personal access tokens with minimum required permissions (`repo:read`, `pull_requests:read`)
- **CI/CD**: Store tokens as encrypted secrets, never in code or config files
- **Cache**: The `.mergeguard-cache/` directory may contain file content from your repository. Add it to `.gitignore`
- **LLM**: When using LLM features, code snippets are sent to the configured provider (OpenAI/Anthropic). Review your organization's data policies before enabling
