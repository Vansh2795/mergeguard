"""Configuration loader for MergeGuard.

Loads .mergeguard.yml with sensible defaults, falling back to
MergeGuardConfig defaults when no config file is present.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from mergeguard.models import MergeGuardConfig

logger = logging.getLogger(__name__)


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

    if "github_url" in raw:
        logger.warning("github_url in config file is ignored (use MERGEGUARD_GITHUB_URL env var)")
        raw.pop("github_url")

    from pydantic import ValidationError

    try:
        return MergeGuardConfig(**raw)
    except ValidationError as exc:
        # Extract unknown field names and retry without them
        unknown_keys = []
        for error in exc.errors():
            if error["type"] == "extra_forbidden" and error.get("loc"):
                unknown_keys.append(str(error["loc"][0]))
        if unknown_keys:
            logger.warning("Unknown config keys (ignored): %s", ", ".join(unknown_keys))
            for key in unknown_keys:
                raw.pop(key, None)
            return MergeGuardConfig(**raw)
        raise
