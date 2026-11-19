import datetime as dt
import json
from unittest.mock import AsyncMock, Mock

import pytest

from companion import reflection
from test_orchestrator import app  # noqa: F401  (fixture)

DAY = dt.date(2026, 11, 18)


def test_transcript_log_and_pending_days(tmp_path):
    logs, vault = tmp_path / 'logs', tmp_path / 'vault'
    reflection.log_turn(logs, 'aku mau ujian jumat', 'Semangat ya!', now=dt.datetime(2026, 11, 18, 21, 5))
    reflection.log_turn(logs, '[Chassie initiative] quiet', 'Lagi ngapain?', initiative=True,
                        now=dt.datetime(2026, 11, 18, 22, 0))
    reflection.log_turn(logs, 'halo', 'Halo!', now=dt.datetime(2026, 11, 19, 8, 0))
    assert reflection.pending_days(logs, vault, today=dt.date(2026, 11, 19)) == [DAY]
    text = reflection.transcript_text(logs, DAY)
    assert '[21:05] Owner: aku mau ujian jumat' in text
    assert 'Chassie (started): Lagi ngapain?' in text and 'initiative' not in text
    reflection.write_note(vault, DAY, 'Hari ini Artdi cerita soal ujian hari Jumat.', ['Tanya hasil ujian Jumat'])
    assert reflection.pending_days(logs, vault, today=dt.date(2026, 11, 19)) == []
    note = (vault / reflection.NOTE_DIR / '2026-11-18.md').read_text()
    assert 'date: 2026-11-18' in note and '- Tanya hasil ujian Jumat' in note


def test_reflection_reply_is_validated():
    summary, loops = reflection.parse_reflection(
        'Sure:\n{"summary":"Artdi belajar untuk ujian dan agak capek.","open_loops":["Tanya ujian"]}')
    assert summary.startswith('Artdi') and loops == ['Tanya ujian']
    for bad in ('no json', '{"summary":"short","open_loops":[]}'):
        with pytest.raises(ValueError):
            reflection.parse_reflection(bad)


def owner(app):
    profile = app._memory.create_profile('Artdi', consent=True)
    app._session_context.set_owner(profile.id)
    app._automatic_memory = True


def test_recall_fuses_keyword_and_semantic_and_includes_recent_diary(app):
    owner(app)
    today = dt.date.today()
    rows = [{'id': 'p', 'path': 'People/Artdi.md', 'content': 'profile', 'kind': 'vault_note', 'updated': '1'},
            {'id': 'd1', 'path': f'{reflection.NOTE_DIR}/{(today - dt.timedelta(days=1)).isoformat()}.md',
             'content': 'diary yesterday', 'kind': 'vault_note', 'updated': '2'},
            {'id': 'd0', 'path': f'{reflection.NOTE_DIR}/2020-01-01.md', 'content': 'old', 'kind': 'vault_note', 'updated': '0'},
            {'id': 's', 'path': 'Events/Exam.md', 'content': 'ujian', 'kind': 'vault_note', 'updated': '1'},
            {'id': 'k', 'path': 'Events/Keyword.md', 'content': 'kata', 'kind': 'vault_note', 'updated': '1'},
            {'id': 'w', 'path': 'Events/Weak.md', 'content': 'weak', 'kind': 'vault_note', 'updated': '1'}]
    app._vault = Mock()
    app._vault.call.side_effect = lambda method, *a, **k: rows if method == 'list' else [rows[4]]
    app._semantic = Mock()
    app._semantic.rank.return_value = [(2.6, rows[3]), (2.1, rows[4]), (1.2, rows[5])]
    sources = [m['source'].split(':', 1)[1] for m in app._vault_recall('capek habis belajar')]
    assert sources[:2] == ['People/Artdi.md', rows[1]['path']]
    assert 'Events/Keyword.md' == sources[2]  # In both lists, so it ranks first.
    assert 'Events/Exam.md' in sources and 'Events/Weak.md' not in sources  # Below the similarity floor.
    assert rows[2]['path'] not in sources  # Stale diary is not forced in.


@pytest.mark.asyncio
async def test_transcript_logged_only_for_owner_scope(app, tmp_path):
    owner(app)
    app._transcripts = tmp_path / 't'
    app._stream_view = {'text': 'Halo!'}
    app._turn_initiative = False
    app._log_transcript('halo')
    assert len(list(app._transcripts.glob('*.jsonl'))) == 1
    app._session_context.mark_guest_present('g', 'Guest')
    app._log_transcript('rahasia tamu')
    assert 'rahasia' not in next(app._transcripts.glob('*.jsonl')).read_text()


@pytest.mark.asyncio
async def test_complete_once_sends_no_history_or_memory_header():
    from hermes_bridge import HermesBridge
    from test_hermes_tts import CONFIG
    bridge = HermesBridge(CONFIG)
    sent = {}

    class Response:
        status = 200
        async def json(self): return {'choices': [{'message': {'content': '{"summary":"x"}'}}]}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def post(url, json=None, **kw):
        sent.update(json=json, kw=kw)
        return Response()
    bridge._session = Mock(post=post)
    bridge._messages.append({'role': 'user', 'content': 'earlier chat'})
    assert await bridge.complete_once('system', 'transcript') == '{"summary":"x"}'
    assert [m['content'] for m in sent['json']['messages']] == ['system', 'transcript']
    assert 'headers' not in sent['kw']
