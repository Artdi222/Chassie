"""Check for and apply updates of a git install: git fetch, then git pull --ff-only.
The AppImage (no .git) checks the latest GitHub release and offers its download instead.

Memory, models and config.local.yaml are git-ignored (the AppImage keeps them in ~/.local/share/chassie),
so an update never touches them.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from brain.config import ROOT

RESTART_CODE = 75  # Desktop exit code that asks launch.py to start Chassie again.
RELEASES = 'https://api.github.com/repos/Artdi222/Chassie/releases/latest'


def _version(text):
    """'v1.2.0' or a build's 'v1.1.0-23-gabc1234' -> (1, 2, 0); a build after a tag counts as that tag."""
    return tuple(int(n) for n in re.findall(r'\d+', (text or '').lstrip('v').split('-')[0])[:3]) or (0,)


def check_release(root=ROOT):
    """The AppImage: is a newer release published? Its .AppImage download link and notes."""
    try: current = (Path(root) / 'VERSION').read_text().strip()
    except OSError: current = 'unknown'
    try:
        with urlopen(Request(RELEASES, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Chassie'}), timeout=20) as response:
            release = json.load(response)
    except HTTPError as exc:
        raise ValueError('No published Chassie release was found' if exc.code == 404 else f'GitHub answered {exc.code}; try again later') from None
    except OSError:
        raise ValueError('Could not reach GitHub; check the internet connection') from None
    latest = release.get('tag_name') or ''
    download = next((a['browser_download_url'] for a in release.get('assets', []) if a.get('name', '').endswith('.AppImage')),
                    release.get('html_url'))
    return {'available': _version(latest) > _version(current), 'behind': 0, 'latest': latest, 'current': current,
            'notes': (release.get('body') or '').strip()[:4000], 'local_changes': [], 'download': download, 'appimage': True}


def _git(root, *args, timeout=60):
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError((exc.stderr or exc.stdout or 'git failed').strip().splitlines()[-1]) from None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        raise ValueError('git did not answer; check the internet connection') from None


def check(root=ROOT):
    if not (Path(root) / '.git').exists(): return check_release(root)
    _git(root, 'fetch', '--tags', '--force', '--quiet', 'origin')
    latest = next(iter(_git(root, 'tag', '-l', 'v*', '--sort=-v:refname').split()), None)
    behind = int(_git(root, 'rev-list', '--count', 'HEAD..@{u}'))
    return {'available': behind > 0, 'behind': behind, 'latest': latest,
            'current': _git(root, 'describe', '--tags', '--always', 'HEAD'),
            'notes': _git(root, 'tag', '-l', '--format=%(contents)', latest) if latest else '',
            'local_changes': _git(root, 'diff', '--name-only', 'HEAD').splitlines()}


def apply(root=ROOT):
    status = check(root)
    if status.get('appimage'): raise ValueError('Download the new AppImage with the button above, then open it; her data is kept')
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
