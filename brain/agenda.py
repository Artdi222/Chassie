"""What Chassie wants to bring up next, and how her initiatives land.

AgendaStore holds things on her mind (follow-ups, her own promises, curiosities, things to
share), written by the model's {"agenda":...} lines and the daily diary's open loops.
SignalLog records, without any model call, which initiatives were spoken and which the owner
answered, so their timing can adapt; closing the app simply leaves one unanswered.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from uuid import uuid4

from brain.reminders import read_json_list, write_json_list

KINDS = ('follow_up', 'promise', 'curiosity', 'share')
MAX_ATTEMPTS = 2           # Raised this often without being resolved: dropped, never nagged.
LIFETIME = dt.timedelta(days=14)
WINDOW_HOURS = 2           # Acceptance pools signals within this many hours of the clock.
HISTORY = dt.timedelta(days=30)


def _iso(value):
    return value.isoformat(timespec='minutes')


class AgendaStore:
    def __init__(self, path):
        self.path = Path(path)

    def list(self):
        return read_json_list(self.path)

    def add(self, text, kind, *, source, earliest=None, expires=None, priority=.5, now=None):
        now = now or dt.datetime.now()
        text = ' '.join(str(text).split())
        if not 3 <= len(text) <= 200 or kind not in KINDS:
            raise ValueError('Agenda items need 3-200 characters and a known kind')
        items = self.list()
        same = next((i for i in items if i['status'] == 'open' and i['text'].casefold() == text.casefold()), None)
        if same:
            return same
        item = {'id': uuid4().hex[:10], 'text': text, 'kind': kind, 'source': str(source)[:80],
                'earliest': _iso(earliest or now), 'expires': _iso(expires or now + LIFETIME),
                'priority': max(0., min(1., float(priority))), 'attempts': 0, 'status': 'open'}
        write_json_list(self.path, items + [item])
        return item

    def open(self, now=None):
        """Open items that may be raised now; expired items are removed from disk."""
        now = _iso(now or dt.datetime.now())
        items = self.list()
        keep = [i for i in items if i['expires'] > now]
        if len(keep) != len(items):
            write_json_list(self.path, keep)
        return [i for i in keep if i['status'] == 'open' and i['earliest'] <= now]

    def top(self, count, now=None):
        # Highest priority first; on a tie the oldest (lowest earliest) wins.
        return sorted(self.open(now), key=lambda i: (-i['priority'], i['earliest']))[:count]

    def best(self, now=None):
        return next(iter(self.top(1, now)), None)

    def _update(self, identifier, change):
        write_json_list(self.path, [change(i) if i['id'] == identifier else i for i in self.list()])

    def raised(self, identifier):
        def bump(item):
            attempts = item['attempts'] + 1
            return {**item, 'attempts': attempts, 'status': 'dropped' if attempts >= MAX_ATTEMPTS else item['status']}
        self._update(identifier, bump)

    def resolve(self, identifier):
        self._update(identifier, lambda item: {**item, 'status': 'done'})


class SignalLog:
    """Append-only JSONL of initiative outcomes: no content, only reason and time."""

    def __init__(self, path):
        self.path = Path(path)
        self._cache = (None, [])

    def add(self, event, reason, now=None):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        entry = {'t': _iso(now or dt.datetime.now()), 'event': event, 'reason': reason}
        with self.path.open('a', encoding='utf-8') as file:
            file.write(json.dumps(entry) + '\n')

    def _entries(self):
        # The initiative loop asks every second: re-parse only when the file changed.
        try:
            stat = self.path.stat()
        except OSError:
            return []
        key = (stat.st_mtime_ns, stat.st_size)
        if self._cache[0] != key:
            entries = []
            for line in self.path.read_text(encoding='utf-8').splitlines():
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
            self._cache = (key, entries)
        return self._cache[1]

    def acceptance(self, reason, hour, now=None):
        """Share of spoken initiatives the owner answered, smoothed: no data gives 0.5."""
        since = _iso((now or dt.datetime.now()) - HISTORY)
        counts = {'raised': 0, 'answered': 0}
        for entry in self._entries():
            if entry.get('reason') != reason or entry.get('t', '') < since or entry.get('event') not in counts:
                continue
            gap = abs(int(entry['t'][11:13]) - hour)
            if min(gap, 24 - gap) <= WINDOW_HOURS:
                counts[entry['event']] += 1
        return (counts['answered'] + 1) / (counts['raised'] + 2)
