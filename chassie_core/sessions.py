"""Owner chat sessions on disk, so reopening Chassie continues the conversation.

One JSON file per session under .chassie/sessions/. Only personal-scope conversations are
saved (the caller checks scope); guests' chats are never written. Messages are the raw
Hermes history (user text and the model's reply lines), not just display text, so a
reopened session gives the model the same context it had.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

MAX_MESSAGES = 2000  # Per session; the oldest are dropped beyond this.
TITLE_LENGTH = 60


def new_session_id():
    return dt.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid4().hex[:6]


class SessionStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{6}', session_id):
            raise ValueError('Unknown chat session')
        return self.directory / f'{session_id}.json'

    def save(self, session_id, messages, skip_title=None):
        """Write the session; the title comes from its first real user message."""
        messages = [{'role': m['role'], 'content': m['content']} for m in messages
                    if m.get('role') in ('user', 'assistant') and isinstance(m.get('content'), str)][-MAX_MESSAGES:]
        if not messages:
            return None
        path = self._path(session_id)
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            previous = {}
        now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        data = {'id': session_id, 'title': previous.get('title') or self._title(messages, skip_title),
                'created': previous.get('created') or now, 'updated': now, 'messages': messages,
                **{k: previous[k] for k in ('summary', 'summary_count') if k in previous}}
        self._write(path, data)
        return data

    def set_summary(self, session_id, summary, count):
        """Store a short recap of the first `count` messages (kept until the chat grows)."""
        data = self.load(session_id)
        data['summary'] = ' '.join(str(summary).split())[:400]
        data['summary_count'] = count
        self._write(self._path(session_id), data)

    def _write(self, path, data):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=self.directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _title(messages, skip=None):
        """First user message, shortened; skip(text) filters Chassie's own initiative cues."""
        for message in messages:
            text = ' '.join(str(message['content']).split())
            if message['role'] == 'user' and text and not (skip and skip(text)):
                return text if len(text) <= TITLE_LENGTH else text[:TITLE_LENGTH - 1].rstrip() + '…'
        return 'Obrolan'

    def load(self, session_id):
        data = json.loads(self._path(session_id).read_text(encoding='utf-8'))
        if not isinstance(data.get('messages'), list):
            raise ValueError('Chat session is damaged')
        return data

    def list(self, limit=50):
        sessions = []
        for path in self.directory.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                sessions.append({'id': data['id'], 'title': data.get('title') or 'Obrolan',
                                 'updated': data.get('updated', ''), 'count': len(data.get('messages', [])),
                                 'summary': data.get('summary'),
                                 'needs_summary': len(data.get('messages', [])) >= 4
                                                  and data.get('summary_count') != len(data.get('messages', []))})
            except (OSError, ValueError, KeyError):
                continue
        sessions.sort(key=lambda s: s['updated'], reverse=True)
        return sessions[:limit]

    def latest(self):
        found = self.list(1)
        return found[0]['id'] if found else None

    def delete(self, session_id):
        path = self._path(session_id)
        if path.exists():
            path.unlink()
