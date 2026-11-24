import json
from unittest.mock import AsyncMock

import pytest

from chassie_core.sessions import SessionStore, new_session_id
from hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG
from test_orchestrator import app


def make_owner(app):
    owner = app._memory.create_profile('Owner', consent=True)
    app._session_context.set_owner(owner.id)
    assert app._personal_scope()


def exchange(n):
    return [{'role': 'user', 'content': f'pesan {n}'}, {'role': 'assistant', 'content': f'balasan {n}'}]


def test_store_saves_lists_loads_and_deletes(tmp_path):
    store = SessionStore(tmp_path / 'sessions')
    first, second = new_session_id(), new_session_id()
    store.save(first, [{'role': 'user', 'content': '[Chassie initiative] quiet'},
                       *exchange(1)], skip_title=lambda text: 'initiative' in text)
    store.save(second, exchange(2))
    data = store.load(first)
    assert data['title'] == 'pesan 1' and len(data['messages']) == 3
    assert {s['id'] for s in store.list()} == {first, second}
    assert (tmp_path / 'sessions' / f'{first}.json').stat().st_mode & 0o777 == 0o600
    store.save(first, exchange(1) + exchange(3))
    assert store.load(first)['title'] == 'pesan 1'  # The title stays once chosen.
    assert store.latest() == first
    store.delete(second)
    assert [s['id'] for s in store.list()] == [first]
    with pytest.raises(ValueError):
        store.load('../../etc/passwd')


def test_bridge_keeps_trimmed_turns_and_resumes_a_window():
    bridge = HermesBridge(CONFIG)
    bridge._max_turns = 2
    history = [m for n in range(5) for m in exchange(n)]
    bridge.load_session('20261124-120000-abcdef', history)
    assert bridge.session_id == '20261124-120000-abcdef'
    window = [m for m in bridge._messages if m['role'] != 'system']
    assert window == history[-4:] and bridge.session_messages() == history
    bridge._messages.extend(exchange(5)); bridge._trim()
    assert bridge.session_messages() == history + exchange(5)  # Trimmed turns are archived, not lost.
    bridge.clear_history()
    assert bridge.session_id is None and bridge.session_messages() == []


@pytest.mark.asyncio
async def test_owner_chats_are_saved_resumed_and_a_new_chat_keeps_the_old_one(app):
    app._broadcast_to_ui = AsyncMock()
    make_owner(app)
    app._hermes = HermesBridge(CONFIG)
    app._hermes._messages.extend(exchange(1))
    app._save_session()
    first = app._hermes.session_id
    assert first and app._sessions.load(first)['messages'] == exchange(1)
    await app.handle_control({'type': 'clear_history'})
    assert app._hermes.session_id is None and app._sessions.load(first)
    app._hermes._messages.extend(exchange(2)); app._save_session()
    second = app._hermes.session_id
    await app.handle_control({'type': 'open_session', 'session_id': first})
    assert app._hermes.session_id == first
    assert [m['content'] for m in app._hermes.get_history() if m['role'] != 'system'] == ['pesan 1', 'balasan 1']
    sent = [c.args[0] for c in app._broadcast_to_ui.call_args_list]
    assert any(m.get('type') == 'history_snapshot' for m in sent)
    listing = [m for m in sent if m.get('type') == 'sessions'][-1]
    assert listing['current'] == first and {s['id'] for s in listing['items']} == {first, second}
    await app.handle_control({'type': 'delete_session', 'session_id': second})
    assert [s['id'] for s in app._sessions.list()] == [first]
    # Restarting continues the latest conversation.
    app._hermes = HermesBridge(CONFIG)
    app._resume_latest_session()
    assert app._hermes.session_id == first and len(app._hermes.session_messages()) == 2


@pytest.mark.asyncio
async def test_guest_conversations_are_never_saved_or_listed(app):
    app._broadcast_to_ui = AsyncMock()
    make_owner(app)
    app._hermes = HermesBridge(CONFIG)
    app._session_context.mark_guest_present('other', 'Friend')
    app._hermes._messages.extend(exchange(1))
    app._save_session()
    assert app._sessions.list() == [] and app._hermes.session_id is None
    assert app._sessions_message()['available'] is False
    with pytest.raises(ValueError):
        await app.handle_control({'type': 'open_session', 'session_id': new_session_id()})
