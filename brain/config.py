"""config.yaml plus optional personal overrides from config.local.yaml (git-ignored)."""
from __future__ import annotations

import json
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


def save_local_persona(text, root=ROOT):
    """Rewrite only companion.persona in config.local.yaml; other keys and comments stay as written."""
    # ponytail: line-based edit (no ruamel); refuses unless the result parses back as expected.
    path = Path(root) / 'config.local.yaml'
    old = path.read_text(encoding='utf-8') if path.is_file() else ''
    lines = old.splitlines()
    entry = '  persona: ' + json.dumps(text, ensure_ascii=False)  # A JSON string is a valid YAML scalar.
    section = next((i for i, line in enumerate(lines) if line.rstrip() == 'companion:'), None)
    if section is None:
        lines += ['companion:', entry]
    else:
        end = next((i for i in range(section + 1, len(lines)) if lines[i].strip() and not lines[i].startswith(' ')), len(lines))
        start = next((i for i in range(section + 1, end) if lines[i].startswith('  persona:')), None)
        if start is None:
            lines.insert(end, entry)
        else:
            stop = next((i for i in range(start + 1, end) if lines[i].strip() and not lines[i].startswith('   ')), end)
            lines[start:stop] = [entry]
    new = '\n'.join(lines) + '\n'
    expected = merge(yaml.safe_load(old) or {}, {'companion': {'persona': text}})
    if yaml.safe_load(new) != expected:
        raise ValueError('config.local.yaml has a layout Chassie cannot edit safely; change the persona there by hand')
    pending = path.with_suffix('.tmp')
    pending.write_text(new, encoding='utf-8')
    pending.replace(path)
