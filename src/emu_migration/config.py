"""Configuration loader with validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load and validate the YAML configuration file.

    Raises FileNotFoundError when the config file is missing and
    ValueError when required keys are absent.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path.resolve()}\n"
            "Copy config.example.yaml → config.yaml and fill in your values."
        )

    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if not isinstance(cfg, dict):
        raise ValueError("Configuration file must be a YAML mapping at the top level.")

    # Allow environment variable overrides for secrets
    _env_override(cfg, "github.token", "GH_TOKEN")
    _env_override(cfg, "entra_id.client_secret", "ENTRA_CLIENT_SECRET")
    _env_override(cfg, "entra_id.tenant_id", "ENTRA_TENANT_ID")

    _validate_required(cfg)
    return cfg


def _env_override(cfg: dict, dotted_key: str, env_var: str) -> None:
    """Override a nested config value from an environment variable if set."""
    value = os.environ.get(env_var)
    if not value:
        return
    keys = dotted_key.split(".")
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


_REQUIRED_KEYS = [
    "github.enterprise",
    "github.organization",
    "github.token",
    "entra_id.tenant_id",
    "entra_id.client_id",
]


def _validate_required(cfg: dict) -> None:
    missing = []
    for dotted in _REQUIRED_KEYS:
        keys = dotted.split(".")
        d = cfg
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                missing.append(dotted)
                break
            d = d[k]
        else:
            if not d or str(d).startswith("REPLACE"):
                missing.append(dotted)
    if missing:
        raise ValueError(
            "Missing or placeholder values in config for: "
            + ", ".join(missing)
        )
