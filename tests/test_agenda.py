import datetime as dt
import json
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from brain.agenda import AgendaStore, SignalLog
from brain.bilingual import BilingualChunker
from test_orchestrator import app, playback_fixture  # noqa: F401  (fixtures)
from test_sessions import make_owner

NOW = dt.datetime(2026, 11, 25, 21, 0)


def test_add_validates_and_dedupes_open_items(tmp_path):
    store = AgendaStore(tmp_path / 'agenda.json')
    item = store.add('Tanya hasil ujian Kamis', 'follow_up', source='diary:2026-11-24', now=NOW)
    assert item['status'] == 'open' and item['attempts'] == 0
    assert item['expires'] == (NOW + dt.timedelta(days=14)).isoformat(timespec='minutes')
    assert store.add('tanya hasil ujian kamis', 'follow_up', source='chat', now=NOW)['id'] == item['id']
    for text, kind in (('ok', 'follow_up'), ('Valid text', 'gossip')):
        with pytest.raises(ValueError):
            store.add(text, kind, source='chat', now=NOW)


def test_open_respects_earliest_and_prunes_expired(tmp_path):
    store = AgendaStore(tmp_path / 'agenda.json')
    later = store.add('Cariin lagu buat belajar', 'promise', source='chat',
                      earliest=NOW + dt.timedelta(hours=2), now=NOW)
    old = store.add('Tanya soal liburan', 'curiosity', source='chat', expires=NOW - dt.timedelta(minutes=1), now=NOW)
    now_item = store.add('Tanya kabar adiknya', 'curiosity', source='chat', now=NOW)
    assert [i['id'] for i in store.open(NOW)] == [now_item['id']]
    assert old['id'] not in {i['id'] for i in store.list()}  # Expired items are dropped from disk.
    assert later['id'] in {i['id'] for i in store.open(NOW + dt.timedelta(hours=3))}


def test_best_prefers_priority_then_oldest(tmp_path):
    store = AgendaStore(tmp_path / 'agenda.json')
    first = store.add('Tanya kabar adiknya', 'curiosity', source='chat', now=NOW)
    store.add('Cerita lagu baru', 'share', source='chat', now=NOW, priority=.3)
    assert store.best(NOW)['id'] == first['id']
    urgent = store.add('Tanya hasil ujian', 'follow_up', source='chat', now=NOW, priority=.9)
    assert store.best(NOW)['id'] == urgent['id']
    assert AgendaStore(tmp_path / 'empty.json').best(NOW) is None


def test_raised_twice_drops_and_resolve_closes(tmp_path):
    store = AgendaStore(tmp_path / 'agenda.json')
    item = store.add('Tanya hasil ujian', 'follow_up', source='chat', now=NOW)
    store.raised(item['id'])
    assert store.open(NOW)[0]['attempts'] == 1
    store.raised(item['id'])
    assert store.open(NOW) == []
    other = store.add('Tanya kabar adiknya', 'curiosity', source='chat', now=NOW)
    store.resolve(other['id'])
    assert store.open(NOW) == []


def test_acceptance_learns_per_reason_and_hour(tmp_path):
    log = SignalLog(tmp_path / 'signals.jsonl')
    assert log.acceptance('quiet', 21, NOW) == .5
    for _ in range(3):
        log.add('raised', 'quiet', NOW)
        log.add('answered', 'quiet', NOW)
    log.add('raised', 'quiet', NOW.replace(hour=9))           # Other hour: ignored.
    log.add('raised', 'agenda', NOW)                           # Other reason: ignored.
    log.add('raised', 'quiet', NOW - dt.timedelta(days=31))    # Too old: ignored.
    assert log.acceptance('quiet', 21, NOW) == pytest.approx(.8)
    assert log.acceptance('quiet', 22, NOW) == pytest.approx(.8)  # Within two hours.
    assert log.acceptance('agenda', 21, NOW) == pytest.approx(1 / 3)


# --- Model lines and wiring -------------------------------------------------------------

PAIR = json.dumps({'emotion': 'happy', 'ja': 'いいね。', 'en': 'Nice.'}, ensure_ascii=False) + '\n'


def test_agenda_lines_are_parsed_and_validated():
    chunker = BilingualChunker('en')
    out = chunker.feed('{"agenda":"Find a study playlist for Owner","kind":"promise","when":"2026-11-26T19:00"}\n'
                       '{"agenda_done":"a1b2c3"}\n' + PAIR)
    assert out[:2] == [('agenda', 'Find a study playlist for Owner', 'promise', '2026-11-26T19:00'),
                       ('agenda_done', 'a1b2c3')]
    assert BilingualChunker('en').feed('{"agenda":"Ask how the trip went","kind":"curiosity"}\n') == [
        ('agenda', 'Ask how the trip went', 'curiosity', None)]
    for bad in ('{"agenda":"Ask","kind":"curiosity"}\n', '{"agenda":"Ask about it","kind":"gossip"}\n',
                '{"agenda":"Ask about it","kind":"promise","x":1}\n', '{"agenda_done":""}\n'):
        with pytest.raises(ValueError):
            BilingualChunker('en').feed(bad)


def agenda_turn(app, lines):
    make_owner(app)
    app._bilingual = True
    app._hermes._stream_timeout = 1
    playback_fixture(app).first_release.set()
    async def synthesize(text, *, emotion):
        yield np.ones(480)
    app._tts.synthesize_stream = synthesize
    async def stream(*a, **kw):
        yield lines + PAIR
    app._hermes.stream_message = stream


@pytest.mark.asyncio
async def test_turn_stores_agenda_items_for_the_owner_only(app):
    agenda_turn(app, '{"agenda":"Find a study playlist for Owner","kind":"promise"}\n')
    await app._run_turn({'text': 'nanti cariin playlist ya', 'source': 'text'})
    assert [i['text'] for i in app._agenda.open()] == ['Find a study playlist for Owner']
    item = app._agenda.open()[0]
    agenda_turn_done = '{"agenda_done":"%s"}\n' % item['id']
    async def stream(*a, **kw):
        yield agenda_turn_done + PAIR
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'udah dapet playlistnya', 'source': 'text'})
    assert app._agenda.open() == []
    app._session_context.mark_guest_present('camera-presence', 'Someone else is present')
    async def guest_stream(*a, **kw):
        yield '{"agenda":"Ask the guest about their trip","kind":"curiosity"}\n' + PAIR
    app._hermes.stream_message = guest_stream
    await app._run_turn({'text': 'halo', 'source': 'text'})
    assert app._agenda.open() == []


@pytest.mark.asyncio
async def test_daily_reflection_turns_open_loops_into_follow_ups(app, tmp_path):
    app._vault = Mock(path=tmp_path / 'vault')
    app._hermes.complete_once = AsyncMock(
        return_value='{"summary":"Owner studied for the Thursday exam and felt tired.","open_loops":["Ask how the exam went"]}')
    day = dt.date(2026, 11, 24)
    from memory import reflection
    reflection.log_turn(app._transcripts, 'besok Kamis aku ujian', 'Semangat ya!', now=dt.datetime(2026, 11, 24, 20, 0))
    await app._reflect_day(day)
    items = app._agenda.open(dt.datetime(2026, 11, 25, 12, 0))
    assert [(i['text'], i['kind'], i['source']) for i in items] == [('Ask how the exam went', 'follow_up', 'diary:2026-11-24')]
    assert items[0]['expires'] == '2026-12-02T00:00'


def test_owner_context_lists_top_agenda_items_but_guests_see_none(app):
    make_owner(app)
    for text, priority in (('Ask how the exam went', .9), ('Find a study playlist', .5), ('Share a new song', .2)):
        app._agenda.add(text, 'follow_up', source='chat', priority=priority)
    agenda = json.loads(app._context_text())['agenda']
    assert [i['text'] for i in agenda['items']] == ['Ask how the exam went', 'Find a study playlist']
    assert all(i['id'] and i['kind'] for i in agenda['items']) and 'agenda_done' in agenda['note']
    app._session_context.mark_guest_present('camera-presence', 'Someone else is present')
    assert 'agenda' not in json.loads(app._context_text())
