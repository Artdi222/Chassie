import subprocess
import pytest
from brain import updates
from test_orchestrator import app  # noqa: F401


def git(cwd, *args):
    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path):
    origin, work, mine = tmp_path / 'origin.git', tmp_path / 'work', tmp_path / 'mine'
    git(tmp_path, 'init', '-q', '--bare', '-b', 'master', str(origin))
    git(tmp_path, 'clone', '-q', str(origin), str(work))
    (work / 'a.txt').write_text('1')
    git(work, 'add', '.'); git(work, 'commit', '-qm', 'one'); git(work, 'tag', '-a', 'v1.0.0', '-m', 'First release')
    git(work, 'push', '-q', '--tags', 'origin', 'master')
    git(tmp_path, 'clone', '-q', str(origin), str(mine))
    return work, mine


def publish(work, text, tag=None):
    (work / 'a.txt').write_text(text)
    git(work, 'commit', '-qam', text)
    if tag: git(work, 'tag', '-a', tag, '-m', 'Notes for ' + tag)
    git(work, 'push', '-q', '--tags', 'origin', 'master')


def test_no_update_when_latest(repos):
    status = updates.check(repos[1])
    assert status['available'] is False and status['latest'] == 'v1.0.0' and status['notes'] == 'First release'


def test_update_pulls_and_reports_notes(repos):
    work, mine = repos
    publish(work, '2', 'v1.10.0'); publish(work, '3', 'v1.2.0')
    status = updates.check(mine)
    assert status['available'] and status['behind'] == 2 and status['latest'] == 'v1.10.0'  # Version order, not text.
    assert status['notes'] == 'Notes for v1.10.0'
    assert updates.apply(mine)['updated'] is True and (mine / 'a.txt').read_text() == '3'
    assert updates.check(mine)['available'] is False


def test_local_changes_refuse_update(repos):
    work, mine = repos
    publish(work, '2')
    (mine / 'a.txt').write_text('edited')
    assert updates.check(mine)['local_changes'] == ['a.txt']
    with pytest.raises(ValueError, match='a.txt'): updates.apply(mine)
    assert (mine / 'a.txt').read_text() == 'edited'


@pytest.mark.asyncio
async def test_update_controls_broadcast_and_restart(repos, app):
    from unittest.mock import AsyncMock
    work, mine = repos
    app._update_root, app._broadcast_to_ui = mine, AsyncMock()
    await app.handle_control({'type': 'check_update'})
    assert app._broadcast_to_ui.call_args_list[0].args[0]['available'] is False
    publish(work, '2'); app._broadcast_to_ui.reset_mock()
    await app.handle_control({'type': 'apply_update'})
    assert [c.args[0]['type'] for c in app._broadcast_to_ui.call_args_list][:2] == ['update', 'restart']
