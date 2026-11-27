"""Check for and apply updates of a git install: git fetch, then git pull --ff-only.

Memory, models and config.local.yaml are git-ignored, so an update never touches them.
"""
from __future__ import annotations

import subprocess

from brain.config import ROOT

RESTART_CODE = 75  # Desktop exit code that asks launch.py to start Chassie again.


def _git(root, *args, timeout=60):
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError((exc.stderr or exc.stdout or 'git failed').strip().splitlines()[-1]) from None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        raise ValueError('git did not answer; check the internet connection') from None


def check(root=ROOT):
    _git(root, 'fetch', '--tags', '--force', '--quiet', 'origin')
    latest = next(iter(_git(root, 'tag', '-l', 'v*', '--sort=-v:refname').split()), None)
    behind = int(_git(root, 'rev-list', '--count', 'HEAD..@{u}'))
    return {'available': behind > 0, 'behind': behind, 'latest': latest,
            'current': _git(root, 'describe', '--tags', '--always', 'HEAD'),
            'notes': _git(root, 'tag', '-l', '--format=%(contents)', latest) if latest else '',
            'local_changes': _git(root, 'diff', '--name-only', 'HEAD').splitlines()}


def apply(root=ROOT):
    status = check(root)
    if status['local_changes']:
        raise ValueError('Update stopped: these files were changed here: ' + ', '.join(status['local_changes']))
    if not status['available']:
        return {**status, 'updated': False}
    before = _git(root, 'rev-parse', 'HEAD')
    _git(root, 'pull', '--ff-only', '--quiet', timeout=300)
    changed = _git(root, 'diff', '--name-only', before, 'HEAD').split()
    if any(name.startswith(('requirements', 'scripts/')) for name in changed):
        # Re-runnable setup: finished parts are skipped; no terminal, so prompts get no answer.
        done = subprocess.run(['bash', 'scripts/setup_linux.sh'], cwd=root, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=1800)
        if done.returncode:
            raise ValueError('Updated, but setup failed; run scripts/setup_linux.sh in a terminal to see why')
    return {**check(root), 'updated': True}
