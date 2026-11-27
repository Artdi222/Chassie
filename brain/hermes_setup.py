"""Hermes setup for people without a terminal: install it, connect it to Chassie and start its gateway.

The official installer runs stage by stage (`--stage NAME --json`), so progress shows in the onboarding page;
stages that need a person at a terminal (provider setup, gateway) are skipped: Chassie configures those itself.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import urllib.request

import yaml

from paths import APP, DATA

INSTALLER = 'https://hermes-agent.nousresearch.com/install.sh'
MODELS_DEV = 'https://models.dev/api.json'
DEV_CACHE = DATA / '.chassie' / 'models-dev.json'  # Used until Hermes writes its own models.dev cache.
TERMINAL_HINT = f'You can also install it in a terminal: curl -fsSL {INSTALLER} | bash'


def hermes_bin():
    found = shutil.which('hermes') or Path.home() / '.local/bin/hermes'
    return str(found) if Path(found).is_file() else None


def key_path(config):
    path = Path(config.get('hermes', {}).get('api_key_file') or '.chassie/hermes-api-key').expanduser()
    return path if path.is_absolute() else DATA / path


def _env(home):
    try: lines = (Path(home) / '.env').read_text(encoding='utf-8').splitlines()
    except OSError: return {}
    return {k.strip(): v.strip() for k, v in (line.split('=', 1) for line in lines if '=' in line)}


def status(home, config):
    """What is done: installed, connected (shared key + API server + memory plugin), running is checked by the caller."""
    home, path = Path(home), key_path(config)
    env = _env(home)
    try: memory = ((yaml.safe_load((home / 'config.yaml').read_text(encoding='utf-8')) or {}).get('memory') or {}).get('provider')
    except (OSError, yaml.YAMLError, AttributeError): memory = None
    key = path.read_text(encoding='utf-8').strip() if path.is_file() else ''
    return {'installed': bool(hermes_bin()),
            'connected': bool(key) and env.get('API_SERVER_KEY') == key and env.get('API_SERVER_ENABLED') == 'true'
                         and memory == 'chassie' and (home / 'plugins/chassie').exists()}


def install(progress):
    """Run the official installer's unattended stages; progress(text) after each."""
    script = DATA / '.chassie' / 'hermes-install.sh'
    script.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(INSTALLER, timeout=60) as response: script.write_bytes(response.read())
    run = lambda *args, timeout=60: subprocess.run(['bash', str(script), *args], stdin=subprocess.DEVNULL,
                                                   capture_output=True, text=True, timeout=timeout)
    stages = [s for s in json.loads(run('--manifest').stdout)['stages'] if not s.get('needs_user_input')]
    for number, stage in enumerate(stages, 1):
        progress(f'Installing Hermes, step {number} of {len(stages)}: {stage["title"]}…')
        done = run('--non-interactive', '--json', '--stage', stage['name'], timeout=1800)
        result = next((json.loads(l) for l in reversed(done.stdout.splitlines()) if l.startswith('{')), {})
        if not result.get('ok'):
            reason = result.get('reason') or (done.stderr.strip().splitlines() or ['it stopped'])[-1]
            raise RuntimeError(f'Hermes could not be installed ({stage["title"]}: {reason[:200]}). {TERMINAL_HINT}')
    if not hermes_bin(): raise RuntimeError(f'Hermes was installed but its command was not found. {TERMINAL_HINT}')


def fetch_models_dev():
    """The provider and model list for the AI model picker (Hermes fetches its own later)."""
    with urllib.request.urlopen(MODELS_DEV, timeout=60) as response: data = response.read(30_000_000)
    json.loads(data)  # Only a valid catalog replaces the old one.
    DEV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    pending = DEV_CACHE.with_suffix('.tmp'); pending.write_bytes(data); pending.replace(DEV_CACHE)


def connect(home, config, write_env):
    """Shared API key, API server on, memory plugin copied and selected, memory folder. Returns the key."""
    home, path = Path(home), key_path(config)
    home.mkdir(parents=True, exist_ok=True)
    key = path.read_text(encoding='utf-8').strip() if path.is_file() else ''
    key = key or secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp'); pending.touch(mode=0o600); pending.chmod(0o600)
    pending.write_text(key, encoding='utf-8'); pending.replace(path)
    url = config.get('hermes', {}).get('gateway_url', 'http://localhost:8642')
    for name, value in [('API_SERVER_ENABLED', 'true'), ('API_SERVER_HOST', '127.0.0.1'),
                        ('API_SERVER_PORT', str(url.rsplit(':', 1)[-1].strip('/') or 8642)), ('API_SERVER_KEY', key)]:
        if _env(home).get(name) != value: write_env(home / '.env', name, value)
    plugin = home / 'plugins' / 'chassie'
    if not plugin.is_symlink():  # A git install of Chassie links its own copy.
        shutil.copytree(APP / 'hermes_plugin' / 'chassie', plugin, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    settings = home / 'chassie.json'
    if not settings.is_file():
        vault = Path.home() / 'Documents' / 'Chassie-Memory'; vault.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({'vault_path': str(vault), 'private_api_session_keys':
                                        [config.get('hermes', {}).get('personal_memory_session_key', 'chassie-owner-memory')]}, indent=1))
    hermes('config', 'set', 'memory.provider', 'chassie')
    return key


def start_gateway():
    hermes('gateway', 'install', '--if-missing', '--start-now', '--start-on-login', timeout=120)
    hermes('gateway', 'restart', timeout=120)  # Reads the new .env.


def hermes(*args, timeout=60):
    command = hermes_bin()
    if not command: raise RuntimeError('Hermes is not installed')
    done = subprocess.run([command, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, 'NO_COLOR': '1'})
    if done.returncode: raise RuntimeError(f'hermes {args[0]} {args[1]} failed: {(done.stderr or done.stdout).strip()[-200:]}')
    return done.stdout
