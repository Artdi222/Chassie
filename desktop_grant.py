"""Short-lived grant that lets Hermes run agent-desktop only for the present owner.

The ~/.local/bin/agent-desktop wrapper refuses GUI actions unless this file
exists, belongs to the current user and holds an unexpired epoch timestamp.
Chassie writes it only for turns whose scope is "personal" (owner present,
no guests) and removes it when the turn's stream ends.
"""
import os
import time
from pathlib import Path


def grant_path() -> Path:
    return Path(f'/run/user/{os.getuid()}') / 'chassie' / 'desktop-grant'


def grant(seconds: float) -> None:
    path = grant_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(str(int(time.time() + seconds)))
    os.replace(tmp, path)


def revoke() -> None:
    try:
        grant_path().unlink()
    except FileNotFoundError:
        pass
