import os
import sqlite3

import pytest

from memory import MemoryStore, SessionContext


def test_explicit_consent_and_persistent_edit_delete(tmp_path):
    path = tmp_path / 'private' / 'memory.sqlite3'
    with MemoryStore(path) as store:
        with pytest.raises(ValueError):
            store.create_profile('Owner', consent=False)
        owner = store.create_profile('Owner', consent=True)
        with pytest.raises(ValueError):
            store.add_memory(owner.id, 'short answers', source='manual', consent=False)
        memory = store.add_memory(owner.id, 'short answers', source='user: remember this', consent=True)
        edited = store.update_memory(owner.id, memory.id, 'detailed answers', source='user correction')
        assert edited.created_at == memory.created_at
        assert edited.source == 'user correction'
    with MemoryStore(path) as store:
        assert store.list_memories(owner.id)[0].content == 'detailed answers'
        assert store.delete_memory(owner.id, memory.id)
        assert store.list_memories(owner.id) == []
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_profile_boundaries_and_cascade(tmp_path):
    path = tmp_path / 'memory.db'
    with MemoryStore(path) as store:
        owner = store.create_profile('Owner', consent=True)
        other = store.create_profile('Other', consent=True)
        secret = store.add_memory(owner.id, 'Private thing', source='manual', consent=True)
        assert not store.delete_memory(other.id, secret.id)
        with pytest.raises(KeyError):
            store.update_memory(other.id, secret.id, 'overwrite', source='manual')
        assert store.list_memories(other.id) == []
        assert store.delete_profile(owner.id)
        with pytest.raises(KeyError):
            store.list_memories(owner.id)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] == 0


def test_validation_and_mutation_revision(tmp_path):
    with MemoryStore(tmp_path / 'memory.db') as store:
        with pytest.raises(ValueError):
            store.create_profile('  ', consent=True)
        with pytest.raises(ValueError):
            store.create_profile('A' * 101, consent=True)
        owner = store.create_profile('Owner', consent=True)
        revision = store.revision
        for content, source in [('', 'manual'), ('a' * 2001, 'manual'), ('valid', '')]:
            with pytest.raises(ValueError):
                store.add_memory(owner.id, content, source=source, consent=True)
        assert store.revision == revision
        store.add_memory(owner.id, 'I prefer English TTS', source='manual', consent=True)
        assert store.revision > revision


def test_uninvited_presence_suspends_personal_and_never_enrolls(tmp_path):
    with MemoryStore(tmp_path / 'memory.db') as store:
        owner = store.create_profile('Owner', consent=True)
        store.add_memory(owner.id, 'Private topic', source='manual', consent=True)
        session = SessionContext(owner_profile_id=owner.id)
        personal = session.context_for_request(store)
        assert personal.scope == 'personal'
        assert personal.memories[0].content == 'Private topic'
        session.mark_guest_present('track-1', 'Visitor')
        shared = session.context_for_request(store)
        assert shared.revision > personal.revision
        assert shared.scope == 'shared'
        assert not shared.memories
        assert len(store.list_profiles()) == 1
        assert not session.guests[0].invited
        session.invite_guest('track-1')
        session.add_shared_note('We are discussing Python')
        assert session.context_for_request(store).shared_notes == ('We are discussing Python',)
        session.set_owner_present(False)
        assert not session.context_for_request(store).memories
        session.remove_guest('track-1')
        assert session.context_for_request(store).scope == 'inactive'
        session.set_owner_present(True)
        assert session.context_for_request(store).scope == 'personal'


def test_clear_invalidates_and_clears_temporary_session_only(tmp_path):
    with MemoryStore(tmp_path / 'memory.db') as store:
        owner = store.create_profile('Owner', consent=True)
        session = SessionContext(owner.id)
        session.mark_guest_present('guest', 'Guest')
        session.invite_guest('guest')
        session.add_shared_note('temporary')
        old = session.revision
        session.clear()
        assert session.revision > old
        assert not session.guests
        assert not session.context_for_request(store).shared_notes
        assert len(store.list_profiles()) == 1
        assert session.mode == 'focus'
        session.set_mode('casual')
        assert session.mode == 'casual'
        with pytest.raises(ValueError):
            session.set_mode('party')
        with pytest.raises(KeyError):
            session.invite_guest('missing')


def test_deleted_owner_fails_closed(tmp_path):
    with MemoryStore(tmp_path / 'memory.db') as store:
        owner = store.create_profile('Owner', consent=True)
        session = SessionContext(owner.id)
        before = session.context_for_request(store)
        store.delete_profile(owner.id)
        after = session.context_for_request(store)
        assert after.scope == 'inactive'
        assert not after.memories
        assert after.memory_revision > before.memory_revision


def test_new_guest_does_not_inherit_earlier_shared_notes(tmp_path):
    with MemoryStore(tmp_path / 'memory.db') as store:
        session = SessionContext()
        session.mark_guest_present('a', 'A')
        session.invite_guest('a')
        session.add_shared_note('shared only with A')
        session.mark_guest_present('b', 'B')
        assert not session.context_for_request(store).shared_notes


def test_sql_text_is_data_and_cross_thread_access(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    with MemoryStore(tmp_path / 'memory.db') as store:
        owner = store.create_profile("Owner'; DROP TABLE memories; --", consent=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            saved = list(pool.map(lambda index: store.add_memory(
                owner.id, f'Memory {index}', source='manual', consent=True), range(20)))
        assert len(saved) == len(store.list_memories(owner.id)) == 20
        assert len(store.list_profiles()) == 1


def test_newer_database_is_not_silently_downgraded(tmp_path):
    path = tmp_path / 'memory.db'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='Unsupported memory schema'):
        MemoryStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 99


def test_store_opens_when_platform_does_not_offer_fchmod(tmp_path, monkeypatch):
    monkeypatch.delattr(os, 'fchmod', raising=False)
    with MemoryStore(tmp_path / 'memory.db') as store:
        profile=store.create_profile('Owner',consent=True)
        assert store.list_profiles()==[profile]
