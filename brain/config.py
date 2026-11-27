"""config.yaml plus optional personal overrides from config.local.yaml (git-ignored)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from paths import APP, DATA

ROOT = APP


def merge(base, override):
    """Nested dicts merge key by key; any other override value replaces the base value."""
    result = dict(base)
    for key, value in (override or {}).items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def load_config(root=ROOT):
    root = Path(root)
    config = yaml.safe_load((root / 'config.yaml').read_text(encoding='utf-8')) or {}
    local = (DATA if root == ROOT else root) / 'config.local.yaml'  # Personal settings live with her data.
    if local.is_file():
        config = merge(config, yaml.safe_load(local.read_text(encoding='utf-8')))
    return config


def save_local(section, values, root=DATA):
    """Rewrite only section.<key> for each key in values in config.local.yaml; other keys and comments stay."""
    # ponytail: line-based edit (no ruamel); refuses unless the result parses back as expected.
    path = Path(root) / 'config.local.yaml'
    old = path.read_text(encoding='utf-8') if path.is_file() else ''
    lines = old.splitlines()
    for key, value in values.items():
        entry = f'  {key}: ' + json.dumps(value, ensure_ascii=False)  # JSON (strings, null) is valid YAML.
        start = next((i for i, line in enumerate(lines) if line.rstrip() == section + ':'), None)
        if start is None:
            lines += [section + ':', entry]
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith(' ')), len(lines))
        at = next((i for i in range(start + 1, end) if lines[i].startswith(f'  {key}:')), None)
        if at is None:
            lines.insert(end, entry)
        else:
            stop = next((i for i in range(at + 1, end) if lines[i].strip() and not lines[i].startswith('   ')), end)
            lines[at:stop] = [entry]
    new = '\n'.join(lines) + '\n'
    if yaml.safe_load(new) != merge(yaml.safe_load(old) or {}, {section: values}):
        raise ValueError('config.local.yaml has a layout Chassie cannot edit safely; change it there by hand')
    pending = path.with_suffix('.tmp')
    pending.write_text(new, encoding='utf-8')
    pending.replace(path)
