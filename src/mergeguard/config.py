"""Configuration loader for MergeGuard.

Loads .mergeguard.yml with sensible defaults, falling back to
MergeGuardConfig defaults when no config file is present.
"""

from __future__ import annotations

from pathlib import Path

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

    try:
        import yaml  # noqa: TCH002
    except ImportError:
        # PyYAML is not a required dependency — fall back to basic parsing
        return _load_without_yaml(path)

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        return MergeGuardConfig()

    return MergeGuardConfig(**raw)


def _load_without_yaml(path: Path) -> MergeGuardConfig:
    """Basic config loading when PyYAML is not installed.

    Supports simple key: value pairs only.
    """
    config_dict: dict = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value.lower() == "true":
                    config_dict[key] = True
                elif value.lower() == "false":
                    config_dict[key] = False
                elif value.isdigit():
                    config_dict[key] = int(value)
                else:
                    config_dict[key] = value.strip('"').strip("'")
    return MergeGuardConfig(**config_dict)
