"""Reminders the owner asked for, kept on disk and spoken by Chassie when they are due.

The model adds one with a reply line {"action":"remind","at":"2026-11-29T16:00","text":"...",
"repeat":"weekly"}; the initiative loop speaks it when due and the owner is there.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

REPEATS = {None: None, 'daily': dt.timedelta(days=1), 'weekly': dt.timedelta(weeks=1)}
STALE = dt.timedelta(hours=12)  # A reminder missed by this much is dropped, not spoken late.


def parse_time(value, now=None):
    """Local, minute-precision time from the model; must be in the future and within a year."""
    now = now or dt.datetime.now()
    if not isinstance(value, str):
        raise ValueError('Reminder time must be text like 2026-11-29T16:00')
    at = dt.datetime.fromisoformat(value.strip())
    if at.tzinfo is not None:
        at = at.astimezone().replace(tzinfo=None)
    at = at.replace(second=0, microsecond=0)
    if at <= now - dt.timedelta(minutes=1) or at > now + dt.timedelta(days=366):
        raise ValueError('Reminder time must be in the coming year')
    return at


def read_json_list(path):
    try:
        items = json.loads(Path(path).read_text(encoding='utf-8'))
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def write_json_list(path, items):
    """Atomic, owner-only write: a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(items, file, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class ReminderStore:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        return read_json_list(self.path)

    def _write(self, items):
        write_json_list(self.path, items)

    def add(self, text, at, repeat=None):
        text = ' '.join(str(text).split())
        if not 3 <= len(text) <= 200:
            raise ValueError('Reminder text must be 3-200 characters')
        if repeat not in REPEATS:
            raise ValueError('Repeat must be daily, weekly or none')
        items = self._read()
        when = at.isoformat(timespec='minutes')
        same = next((i for i in items if i['text'].casefold() == text.casefold() and i['at'] == when), None)
        if same:
            return same
        item = {'id': uuid4().hex[:10], 'text': text, 'at': at.isoformat(timespec='minutes'), 'repeat': repeat}
        self._write(items + [item])
        return item

    def list(self):
        return sorted(self._read(), key=lambda i: i['at'])

    def due(self, now=None):
        """Reminders to speak now; drops one-off reminders missed for too long."""
        now = now or dt.datetime.now()
        items, due, keep, changed = self._read(), [], [], False
        for item in items:
            at = dt.datetime.fromisoformat(item['at'])
            if at > now:
                keep.append(item)
            elif now - at > STALE and not item.get('repeat'):
                changed = True  # Too late to be useful.
            else:
                due.append(item); keep.append(item)
        if changed:
            self._write(keep)
        return due

    def done(self, identifier, now=None):
        """Spoken: a repeating reminder moves to its next time, a one-off is removed."""
        now = now or dt.datetime.now()
        items = []
        for item in self._read():
            if item['id'] == identifier:
                step = REPEATS.get(item.get('repeat'))
                if not step:
                    continue
                at = dt.datetime.fromisoformat(item['at'])
                while at <= now:
                    at += step
                item = {**item, 'at': at.isoformat(timespec='minutes')}
            items.append(item)
        self._write(items)

    def delete(self, identifier):
        self._write([i for i in self._read() if i['id'] != identifier])
