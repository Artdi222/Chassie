"""config.yaml plus optional personal overrides from config.local.yaml (git-ignored)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def merge(base, override):
    """Nested dicts merge key by key; any other override value replaces the base value."""
    result = dict(base)
    for key, value in (override or {}).items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def load_config(root=ROOT):
    root = Path(root)
    config = yaml.safe_load((root / 'config.yaml').read_text(encoding='utf-8')) or {}
    local = root / 'config.local.yaml'
    if local.is_file():
        config = merge(config, yaml.safe_load(local.read_text(encoding='utf-8')))
    return config
