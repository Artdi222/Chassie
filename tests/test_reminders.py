import asyncio
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from brain.bilingual import BilingualChunker
from brain.reminders import ReminderStore, parse_time
from brain.hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG
from test_orchestrator import app
from test_sessions import exchange, make_owner

NOW = dt.datetime(2026, 11, 24, 20, 0)


def test_parse_time_accepts_the_coming_year_only():
    assert parse_time('2026-11-29T16:00', NOW) == dt.datetime(2026, 11, 29, 16, 0)
    for bad in ('2026-11-20T10:00', '2028-01-01T10:00', 'Saturday', None):
        with pytest.raises((ValueError, TypeError)):
            parse_time(bad, NOW)


def test_reminders_fire_repeat_and_expire(tmp_path):
    store = ReminderStore(tmp_path / 'reminders.json')
    once = store.add('Les gitar', dt.datetime(2026, 11, 29, 16, 0))
    weekly = store.add('Latihan gitar', dt.datetime(2026, 11, 25, 19, 0), 'weekly')
    assert store.add('les  gitar', dt.datetime(2026, 11, 29, 16, 0))['id'] == once['id']  # No duplicate.
    assert store.due(NOW) == []
    assert [r['id'] for r in store.due(dt.datetime(2026, 11, 25, 19, 1))] == [weekly['id']]
    store.done(weekly['id'], dt.datetime(2026, 11, 25, 19, 1))
    assert next(r for r in store.list() if r['id'] == weekly['id'])['at'] == '2026-12-02T19:00'
    assert store.due(dt.datetime(2026, 11, 30, 10, 0)) == []  # Missed by more than 12 hours: dropped.
    assert [r['id'] for r in store.list()] == [weekly['id']]
    store.delete(weekly['id'])
    assert store.list() == []


def test_remind_action_line_parses_anywhere():
    chunker = BilingualChunker('en')
    pair = json.dumps({'emotion': 'happy', 'ja': 'わかった。', 'en': 'Okay.'}, ensure_ascii=False)
    line = '{"action":"remind","at":"2026-11-29T16:00","text":"Les gitar","repeat":"weekly"}'
    assert chunker.feed(pair + '\n' + line + '\n')[1] == ('action', 'remind', {'at': '2026-11-29T16:00', 'text': 'Les gitar', 'repeat': 'weekly'})
    with pytest.raises(ValueError):
        BilingualChunker('en').feed('{"action":"remind","at":"2026-11-29T16:00","text":"x","repeat":"monthly"}\n')


@pytest.mark.asyncio
async def test_owner_reminder_is_saved_and_spoken_when_due(app):
    app._broadcast_to_ui = AsyncMock()
    await app._run_model_action('ingetin aku', 'remind', {'at': '2026-11-29T16:00', 'text': 'Les gitar', 'repeat': None})
    assert app._reminders.list() == []  # Not personal scope yet: nothing saved.
    make_owner(app)
    at = (dt.datetime.now() + dt.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M')
    await app._run_model_action('ingetin aku', 'remind', {'at': at, 'text': 'Les gitar', 'repeat': None})
    assert [r['text'] for r in app._reminders.list()] == ['Les gitar']
    notices = [c.args[0]['text'] for c in app._broadcast_to_ui.call_args_list if c.args[0].get('type') == 'notice']
    assert notices[-1].startswith('Reminder set: Les gitar')
    # Make it due, then let the initiative loop run one tick.
    app._reminders.add('Minum air', dt.datetime.now().replace(second=0, microsecond=0) - dt.timedelta(minutes=1))
    app._running = True
    app._vision = None
    started = AsyncMock()
    app._start_initiative = started
    app._track_presence = lambda now: True
    task = asyncio.create_task(app._initiative_loop())
    for _ in range(30):
        await asyncio.sleep(.1)
        if started.await_count: break
    app._running = False; task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert started.await_args.args[:2] == ('reminder', 'Minum air')
    assert [r['text'] for r in app._reminders.list()] == ['Les gitar']


@pytest.mark.asyncio
async def test_left_session_is_summarized_and_recalled_in_the_next_chat(app):
    make_owner(app)
    app._broadcast_to_ui = AsyncMock()
    app._hermes = HermesBridge(CONFIG)
    app._hermes.complete_once = AsyncMock(return_value='Artdi cerita soal les gitar barunya.')
    for n in range(2): app._hermes._messages.extend(exchange(n))
    app._save_session()
    first = app._hermes.session_id
    await app.handle_control({'type': 'clear_history'})
    await asyncio.gather(*app._summary_tasks)
    assert app._sessions.load(first)['summary'] == 'Artdi cerita soal les gitar barunya.'
    context = json.loads(app._context_text())
    assert context['previous_chat']['summary'] == 'Artdi cerita soal les gitar barunya.'
    assert 'local_time' in context
    listing = app._sessions_message()
    assert listing['items'][0]['summary'] and listing['items'][0]['needs_summary'] is False
