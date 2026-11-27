"""Providers and models as Hermes knows them: its signed-in credentials and its own model catalog caches.

Nothing here is a hand-kept list: `hermes auth list` says which providers are signed in, and the
models.dev cache (plus Hermes's catalog for OpenRouter/Nous) lists their models and abilities.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

# Hermes provider id -> models.dev id where the two differ.
# ponytail: two known differences; add one when a signed-in provider shows no models.
MODELS_DEV_IDS = {'openai-api': 'openai', 'gemini': 'google'}


def hermes_home():
    return Path(os.environ.get('HERMES_HOME', '~/.hermes')).expanduser()


def _json(path):
    try: data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}
    return data if isinstance(data, dict) else {}


def signed_in(auth_output=None):
    """Provider ids with a Hermes credential. Only ids are read: account names and e-mails are skipped."""
    if auth_output is None:
        try: auth_output = subprocess.run(['hermes', 'auth', 'list'], stdin=subprocess.DEVNULL, capture_output=True,
                                         text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError): auth_output = ''
    return re.findall(r'^([\w.:-]+) \(\d+ credentials?\):', auth_output, re.M)


def providers(home=None, auth_output=None):
    """[{id, label, signed_in, key_name}]: signed-in providers first, then every provider models.dev knows."""
    home = Path(home or hermes_home())
    dev, hermes = _json(home / 'models_dev_cache.json'), _json(home / 'cache/model_catalog.json').get('providers', {})
    def label(pid):
        info = dev.get(MODELS_DEV_IDS.get(pid, pid)) or {}
        return info.get('name') or (hermes.get(pid) or {}).get('metadata', {}).get('display_name') or pid
    mine = signed_in(auth_output)
    rest = sorted((set(dev) | set(hermes)) - set(mine) - {MODELS_DEV_IDS.get(p, p) for p in mine})
    return [{'id': pid, 'label': label(pid), 'signed_in': pid in mine, 'key_name': key_name(home, pid)} for pid in [*mine, *rest]]


def key_name(home, provider):
    env = (_json(Path(home) / 'models_dev_cache.json').get(MODELS_DEV_IDS.get(provider, provider)) or {}).get('env') or []
    return env[0] if env else None


def models(home, provider):
    """[{id, name, vision, reasoning}] for one provider; vision/reasoning None when the catalog does not say."""
    home = Path(home)
    info = _json(home / 'models_dev_cache.json').get(MODELS_DEV_IDS.get(provider, provider))
    if info:
        return [{'id': mid, 'name': m.get('name') or mid, 'vision': 'image' in (m.get('modalities') or {}).get('input', []),
                 'reasoning': bool(m.get('reasoning'))} for mid, m in (info.get('models') or {}).items()]
    listed = (_json(home / 'cache/model_catalog.json').get('providers', {}).get(provider) or {}).get('models', [])
    return [{'id': m['id'], 'name': m['id'], 'vision': None, 'reasoning': None} for m in listed if isinstance(m, dict) and m.get('id')]
