"""Runtime config loading + the reproducibility hash recorded on every RunRecord.

CLAUDE.md: "All randomness seeded from config. `config_hash` recorded on every RunRecord." The hash is
over the fully-resolved config (defaults + overrides), serialized with sorted keys so dict ordering
can never change it.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into a copy of `base` (override wins on leaf conflicts)."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    """config/default.yaml, optionally overlaid by another YAML file and then by an in-memory dict."""
    with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG_PATH:
        with Path(path).open(encoding="utf-8") as f:
            config = deep_merge(config, yaml.safe_load(f) or {})
    if overrides:
        config = deep_merge(config, overrides)
    return config


def config_hash(config: dict[str, Any]) -> str:
    """Stable 16-hex-char digest of a resolved config."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def resolve_path(value: str | Path) -> Path:
    """Config paths are repo-relative unless absolute."""
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path
