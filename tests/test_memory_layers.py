import json
import shutil
from pathlib import Path

import pytest

from memory.vault import VaultMemory


def vault_memory(tmp_path):
    home = tmp_path / 'hermes'; plugin = home / 'plugins/chassie'; plugin.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[1] / 'hermes_plugin/chassie/store.py', plugin / 'store.py')
    vault = tmp_path / 'Memory'; vault.mkdir()
    (home / 'chassie.json').write_text(json.dumps({'vault_path': str(vault)}))
    return VaultMemory(home)


def test_facts_carry_importance_and_notice_owner_edits(tmp_path):
    memory = vault_memory(tmp_path)
    saved = memory.call('remember', 'Owner drinks coffee without sugar every morning.', title='Coffee')
    fact = next(f for f in memory.call('facts') if f['id'] == saved['id'])
    assert fact['content'] == 'Owner drinks coffee without sugar every morning.'
    assert fact['importance'] == 2 and fact['superseded_by'] is None and fact['edited'] is False
    path = memory.path / saved['source_file']
    path.write_text(path.read_text().replace('without sugar', 'with a little honey'))
    assert next(f for f in memory.call('facts') if f['id'] == saved['id'])['edited'] is True


def test_mark_supersedes_and_rates_only_managed_facts(tmp_path):
    memory = vault_memory(tmp_path)
    (memory.path / 'Handwritten.md').write_text('My own note about coffee.')
    old = memory.call('remember', 'Owner drinks coffee every morning.')
    new = memory.call('remember', 'Owner stopped drinking coffee in November.')
    memory.call('mark', old['id'], superseded_by=new['id'])
    memory.call('mark', new['id'], importance=3)
    facts = {f['id']: f for f in memory.call('facts')}
    assert facts[old['id']]['superseded_by'] == new['id'] and facts[new['id']]['importance'] == 3
    kinds = {r['path']: r['kind'] for r in memory.call('list', 50)}
    assert kinds[old['source_file']] == 'superseded' and kinds[new['source_file']] == 'user_statement'
    handwritten = next(r['id'] for r in memory.call('list', 50) if r['path'] == 'Handwritten.md')
    for bad in ((handwritten, {'importance': 3}), (old['id'], {'importance': 7}),
                (old['id'], {'superseded_by': old['id']}), (old['id'], {'superseded_by': 'f' * 24})):
        with pytest.raises(ValueError):
            memory.call('mark', bad[0], **bad[1])


def test_memory_log_is_never_indexed_or_listed(tmp_path):
    memory = vault_memory(tmp_path)
    memory.call('remember', 'Owner plays the guitar on weekends.')
    log = memory.path / '_generated/chassie/Memory log.md'
    log.write_text('# Memory log\n\n- superseded something because of a long reason\n')
    assert not any(r['path'].endswith('Memory log.md') for r in memory.call('list', 50))
    assert 'Memory log' not in (memory.path / '_generated/chassie/Memories.md').read_text()
    assert all(not f['path'].endswith('Memory log.md') for f in memory.call('facts'))


# --- Consolidation -----------------------------------------------------------------------

import asyncio  # noqa: E402

from memory import consolidation  # noqa: E402

A, B, C = 'a' * 24, 'b' * 24, 'c' * 24


def test_ops_are_validated_against_the_batch():
    reply = json.dumps({'ops': [
        {'op': 'supersede', 'old': A, 'by': B, 'why': 'stopped drinking coffee'},
        {'op': 'supersede', 'old': A, 'by': A, 'why': 'self'},           # Same fact.
        {'op': 'supersede', 'old': C, 'by': B, 'why': 'edited by owner'},  # Protected.
        {'op': 'supersede', 'old': 'd' * 24, 'by': B, 'why': 'unknown'},   # Not in the batch.
        {'op': 'importance', 'id': B, 'level': 3},
        {'op': 'importance', 'id': B, 'level': 9},
        {'op': 'delete', 'id': A}]})
    ops = consolidation.parse_ops('Sure!\n' + reply, new_ids={B}, all_ids={A, B, C}, protected={C})
    assert ops == [{'op': 'supersede', 'old': A, 'by': B, 'why': 'stopped drinking coffee'},
                   {'op': 'importance', 'id': B, 'level': 3}]
    with pytest.raises(ValueError):
        consolidation.parse_ops('no json here', new_ids={B}, all_ids={A, B}, protected=set())


def test_consolidation_supersedes_logs_backs_up_and_writes_a_profile(tmp_path):
    memory = vault_memory(tmp_path)
    old = memory.call('remember', 'Owner drinks coffee every morning.')
    new = memory.call('remember', 'Owner stopped drinking coffee in November.')
    edited = memory.call('remember', 'Owner has a sister called Rina.')
    path = memory.path / edited['source_file']
    path.write_text(path.read_text().replace('Rina', 'Rani'))
    calls = []

    async def complete_once(system, text):
        calls.append((system, text))
        if len(calls) == 1:
            return json.dumps({'ops': [
                {'op': 'supersede', 'old': old['id'], 'by': new['id'], 'why': 'they stopped in November'},
                {'op': 'supersede', 'old': edited['id'], 'by': new['id'], 'why': 'wrong'},
                {'op': 'importance', 'id': new['id'], 'level': 3}]})
        return '## People\n- Sister Rani\n\n## Likes and dislikes\n- No coffee since November\n' + 'x' * 3000

    state = tmp_path / 'state'
    run = lambda: asyncio.run(consolidation.consolidate(
        memory.call, complete_once, state_dir=state, vault_path=memory.path,
        similar=lambda fact, active: [f['id'] for f in active if f['id'] != fact['id']]))
    summary = run()
    assert summary == {'new': 3, 'superseded': 1, 'profile': True}
    facts = {f['id']: f for f in memory.call('facts')}
    assert facts[old['id']]['superseded_by'] == new['id'] and facts[edited['id']]['superseded_by'] is None
    assert facts[new['id']]['importance'] == 3
    log = (memory.path / '_generated/chassie/Memory log.md').read_text()
    assert 'Owner drinks coffee every morning.' in log and 'they stopped in November' in log
    assert len(list((state / 'memory-backups').glob('*.zip'))) == 1
    profile = (memory.path / '_generated/chassie-profile.md').read_text()
    assert 'Sister Rani' in profile and len(profile) <= 2200
    assert 'Owner drinks coffee every morning.' not in calls[1][1]  # Superseded facts stay out of the profile.
    assert run() == {'new': 0, 'superseded': 0, 'profile': False} and len(calls) == 2  # Nothing new: no model call.


# --- Recall ------------------------------------------------------------------------------

import datetime as dt  # noqa: E402
from unittest.mock import AsyncMock, Mock  # noqa: E402

from test_orchestrator import app  # noqa: F401,E402
from test_sessions import make_owner  # noqa: E402


def stamp(days_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()


def test_recall_layers_profile_scored_facts_and_linked_entities(app):
    make_owner(app)  # "Owner"
    app._automatic_memory = True
    fact = lambda name, days, kind='user_statement': {'path': f'_generated/chassie/{name}.md', 'content': name,
                                                     'kind': kind, 'updated': stamp(days)}
    rows = [{'path': 'People/Owner.md', 'content': 'owner note', 'kind': 'vault_note', 'updated': stamp(1)},
            {'path': '_generated/chassie-profile.md', 'content': 'profile', 'kind': 'vault_note', 'updated': stamp(1)},
            fact('gone', 0, 'superseded'), fact('trivial', 0), *(fact(f'normal{i}', 1) for i in range(5)),
            fact('core', 10),
            {'path': 'People/Rina.md', 'content': 'Rina is their sister', 'kind': 'vault_note', 'updated': stamp(30)},
            {'path': 'Places/Bandung.md', 'content': 'Bandung trip notes', 'kind': 'vault_note', 'updated': stamp(30)}]
    hits = [{'path': 'Events/Hike.md', 'content': 'Hiking with [[Rina]] and [[Owner]], see [[Memories]]'},
            {'path': '_generated/chassie/gone.md', 'content': 'gone', 'kind': 'superseded'}]
    app._vault = Mock()
    app._vault.call.side_effect = lambda method, *a, **k: rows if method == 'list' else hits
    app._fact_importance = {'_generated/chassie/trivial.md': 1, '_generated/chassie/core.md': 3}
    sources = [m['source'].split(':', 1)[1] for m in app._vault_recall('cerita soal Bandung dong')]
    facts = [s for s in sources if s.startswith('_generated/chassie/')]
    assert sources[:2] == ['People/Owner.md', '_generated/chassie-profile.md']
    assert facts[0] == '_generated/chassie/core.md' and len(facts) == 6
    assert '_generated/chassie/trivial.md' not in facts and '_generated/chassie/gone.md' not in sources
    assert sources[-3:] == ['Events/Hike.md', 'People/Rina.md', 'Places/Bandung.md']


@pytest.mark.asyncio
async def test_idle_consolidation_runs_on_the_vault_and_refreshes_importance(app, tmp_path):
    make_owner(app)
    app._automatic_memory = True
    app._vault = vault_memory(tmp_path)
    saved = app._vault.call('remember', 'Owner has a sister called Rina.')
    app._hermes.complete_once = AsyncMock(side_effect=[
        json.dumps({'ops': [{'op': 'importance', 'id': saved['id'], 'level': 3}]}), '## People\n- Sister Rina'])
    assert (await app._consolidate())['new'] == 1
    assert app._fact_importance[saved['source_file']] == 3
    assert (await app._consolidate())['new'] == 0


def test_profile_waits_for_the_last_batch(tmp_path):
    memory = vault_memory(tmp_path)
    for i in range(consolidation.BATCH + 1):
        memory.call('remember', f'Owner fact number {i} about their week.')
    calls = []
    async def complete_once(system, text):
        calls.append(system)
        return '{"ops":[]}' if system == consolidation.SYSTEM else '## People\n- Someone'
    run = lambda: asyncio.run(consolidation.consolidate(memory.call, complete_once, state_dir=tmp_path / 'state',
                                                        vault_path=memory.path, similar=lambda fact, active: []))
    assert run() == {'new': consolidation.BATCH, 'superseded': 0, 'profile': False}
    assert run() == {'new': 1, 'superseded': 0, 'profile': True}
    assert calls.count(consolidation.SYSTEM) == 2 and len(calls) == 3
