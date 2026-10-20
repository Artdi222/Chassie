"""Small, consent-based local store. Profile selection is not authentication."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import json
import math
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from face_identity import TEMPLATE_MODEL, TEMPLATE_SIZE


def bounded_text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{name} must contain 1–{maximum} characters without NUL')
    return value.strip()


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    created_at: str


@dataclass(frozen=True)
class Memory:
    id: str
    profile_id: str
    content: str
    source: str
    created_at: str
    updated_at: str


class MemoryStore:
    """SQLite storage with explicit opt-in and scoped CRUD.

    Use a dedicated application data directory. Unix database permissions are
    restricted to its owner. Windows inherits the directory ACL: chmod does not
    establish an equivalent private ACL. This is not encryption or secure
    erasure of filesystem backups. No audio/video or inferred text memories are
    stored. Explicit face enrollment saves an ArcFace template in a separate table.
    ``revision`` invalidates in-flight context
    whenever stored data changes.
    """

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError('Memory database must not be a symlink')
        # Create privately before SQLite opens it; never chmod an existing parent.
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if hasattr(os, 'fchmod'):
                os.fchmod(fd, 0o600)
            else:
                # Windows does not expose fchmod. Its directory ACL remains the
                # access boundary; chmod alone is not an ACL privacy guarantee.
                os.chmod(path, 0o600)
        finally:
            os.close(fd)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.execute('PRAGMA secure_delete=ON')
        version = self._db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise ValueError(f'Unsupported memory schema version: {version}')
        with self._db:
            self._db.executescript('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    content TEXT NOT NULL, source TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY, value INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS face_templates (
                    profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
                    embedding TEXT NOT NULL, model TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS voice_templates (
                    profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
                    embedding TEXT NOT NULL, model TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO metadata VALUES ('revision', 0);
                PRAGMA user_version=1;
            ''')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        with self._lock:
            self._db.close()

    @property
    def revision(self):
        with self._lock:
            return self._db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0]

    def _changed(self):
        self._db.execute("UPDATE metadata SET value=value+1 WHERE key='revision'")

    def _require_profile(self, profile_id):
        if not self._db.execute('SELECT 1 FROM profiles WHERE id=?', (profile_id,)).fetchone():
            raise KeyError('Profile does not exist')

    def create_profile(self, name, *, consent):
        if consent is not True:
            raise ValueError('Explicit consent is required to create a local profile')
        name = bounded_text(name, 'name', 100)
        with self._lock, self._db:
            if self._db.execute('SELECT COUNT(*) FROM profiles').fetchone()[0] >= 32:
                raise ValueError('Maximum of 32 local profiles reached')
            record = Profile(uuid4().hex, name, datetime.now(timezone.utc).isoformat())
            self._db.execute('INSERT INTO profiles VALUES (?,?,?)', (record.id, record.name, record.created_at))
            self._changed()
            return record

    def list_profiles(self):
        with self._lock:
            return [Profile(**dict(row)) for row in self._db.execute('SELECT * FROM profiles ORDER BY created_at, id')]

    def delete_profile(self, profile_id):
        with self._lock, self._db:
            changed = self._db.execute('DELETE FROM profiles WHERE id=?', (profile_id,)).rowcount > 0
            if changed:
                self._changed()
            return changed

    def add_memory(self, profile_id, content, *, source, consent):
        if consent is not True:
            raise ValueError('Explicit consent is required to save a personal memory')
        content = bounded_text(content, 'content', 2000)
        source = bounded_text(source, 'source', 200)
        with self._lock, self._db:
            self._require_profile(profile_id)
            if self._db.execute('SELECT COUNT(*) FROM memories WHERE profile_id=?', (profile_id,)).fetchone()[0] >= 500:
                raise ValueError('Maximum of 500 memories per profile reached')
            now = datetime.now(timezone.utc).isoformat()
            record = Memory(uuid4().hex, profile_id, content, source, now, now)
            self._db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?)',
                             (record.id, record.profile_id, record.content, record.source, now, now))
            self._changed()
            return record

    def update_memory(self, profile_id, memory_id, content, *, source):
        content = bounded_text(content, 'content', 2000)
        source = bounded_text(source, 'source', 200)
        with self._lock, self._db:
            now = datetime.now(timezone.utc).isoformat()
            changed = self._db.execute(
                'UPDATE memories SET content=?, source=?, updated_at=? WHERE id=? AND profile_id=?',
                (content, source, now, memory_id, profile_id)).rowcount
            if not changed:
                raise KeyError('Memory does not exist for this profile')
            self._changed()
            return Memory(**dict(self._db.execute('SELECT * FROM memories WHERE id=?', (memory_id,)).fetchone()))

    def delete_memory(self, profile_id, memory_id):
        with self._lock, self._db:
            changed = self._db.execute('DELETE FROM memories WHERE id=? AND profile_id=?', (memory_id, profile_id)).rowcount > 0
            if changed:
                self._changed()
            return changed

    def list_memories(self, profile_id):
        with self._lock:
            self._require_profile(profile_id)
            return [Memory(**dict(row)) for row in self._db.execute(
                'SELECT * FROM memories WHERE profile_id=? ORDER BY created_at, id', (profile_id,))]

    def snapshot(self, profile_id):
        """Return a consistent in-process pair of revision and profile memories."""
        with self._lock:
            try:
                memories = tuple(self.list_memories(profile_id))
            except KeyError:
                memories = None
            return self.revision, memories

    def save_face(self, profile_id, embedding, *, consent):
        if consent is not True:
            raise ValueError('Explicit consent is required to remember a face')
        if (not isinstance(embedding, list) or len(embedding) != TEMPLATE_SIZE
                or any(type(v) not in (float, int) or not math.isfinite(v) for v in embedding)
                or sum(v*v for v in embedding) < 1e-12):
            raise ValueError('Invalid face template')
        with self._lock, self._db:
            self._require_profile(profile_id)
            self._db.execute('INSERT OR REPLACE INTO face_templates VALUES (?,?,?,?)',
                             (profile_id, json.dumps(embedding), TEMPLATE_MODEL, datetime.now(timezone.utc).isoformat()))
            self._changed()

    def list_faces(self):
        with self._lock:
            return [{'profile_id': row['profile_id'], 'name': row['name'], 'embedding': json.loads(row['embedding'])}
                    for row in self._db.execute('SELECT f.*, p.name FROM face_templates f JOIN profiles p ON p.id=f.profile_id WHERE model=?', (TEMPLATE_MODEL,))]

    def delete_face(self, profile_id):
        with self._lock, self._db:
            changed = self._db.execute('DELETE FROM face_templates WHERE profile_id=?', (profile_id,)).rowcount > 0
            if changed:
                self._changed()
            return changed

    def save_voice(self,profile_id,embedding,*,consent):
        if consent is not True:raise ValueError('Explicit consent is required to remember a voice')
        if (not isinstance(embedding,list) or len(embedding)!=256 or
                any(type(v) not in (float,int) or not math.isfinite(v) for v in embedding) or
                sum(v*v for v in embedding)<1e-12):raise ValueError('Invalid voice template')
        with self._lock,self._db:
            self._require_profile(profile_id)
            self._db.execute('INSERT OR REPLACE INTO voice_templates VALUES (?,?,?,?)',
                (profile_id,json.dumps(embedding),'wespeaker-resnet34',datetime.now(timezone.utc).isoformat()))
            self._changed()

    def list_voices(self):
        with self._lock:
            return [{'profile_id':row['profile_id'],'name':row['name'],'embedding':json.loads(row['embedding'])}
                for row in self._db.execute('SELECT v.*,p.name FROM voice_templates v JOIN profiles p ON p.id=v.profile_id WHERE model=?',('wespeaker-resnet34',))]

    def delete_voice(self,profile_id):
        with self._lock,self._db:
            changed=self._db.execute('DELETE FROM voice_templates WHERE profile_id=?',(profile_id,)).rowcount>0
            if changed:self._changed()
            return changed
