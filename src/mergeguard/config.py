"""Configuration loader for MergeGuard.

Loads .mergeguard.yml with sensible defaults, falling back to
MergeGuardConfig defaults when no config file is present.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mergeguard.models import MergeGuardConfig


def load_config(config_path: str = ".mergeguard.yml") -> MergeGuardConfig:
    """Load MergeGuard configuration from a YAML file.

    Falls back to default configuration if the file doesn't exist.

    Args:
        config_path: Path to the .mergeguard.yml file.

    Returns:
        Validated MergeGuardConfig instance.
    """
    path = Path(config_path)
    if not path.exists():
        return MergeGuardConfig()

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        return MergeGuardConfig()

    return MergeGuardConfig(**raw)
