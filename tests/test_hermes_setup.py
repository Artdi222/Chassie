"""Onboarding → Brain: install, connect and start Hermes without a terminal (fakes only; the real Hermes is untouched)."""
import json
import pytest
import yaml
from brain import hermes_setup
from brain.controls import write_env
from test_orchestrator import app  # noqa: F401


@pytest.fixture
def fake(tmp_path, monkeypatch):
    log = tmp_path / 'calls.txt'
    tool = tmp_path / 'bin/hermes'; tool.parent.mkdir()
    tool.write_text(f'#!/bin/sh\necho "$@" >> {log}\n'); tool.chmod(0o755)
    monkeypatch.setattr(hermes_setup, 'hermes_bin', lambda: str(tool))
    monkeypatch.setattr(hermes_setup.Path, 'home', lambda: tmp_path)
    home = tmp_path / '.hermes'
    config = {'hermes': {'api_key_file': str(tmp_path / 'data/hermes-api-key'), 'gateway_url': 'http://localhost:8642'}}
    return home, config, log


def test_connect_shares_a_key_and_turns_on_the_api_and_memory(fake):
    home, config, log = fake
    key = hermes_setup.connect(home, config, write_env)
    env = dict(line.split('=', 1) for line in (home / '.env').read_text().split())
    assert env == {'API_SERVER_ENABLED': 'true', 'API_SERVER_HOST': '127.0.0.1', 'API_SERVER_PORT': '8642', 'API_SERVER_KEY': key}
    assert len(key) == 64 and (home / '.env').stat().st_mode & 0o777 == 0o600
    assert hermes_setup.key_path(config).read_text() == key and hermes_setup.key_path(config).stat().st_mode & 0o777 == 0o600
    assert (home / 'plugins/chassie/__init__.py').is_file()
    assert json.loads((home / 'chassie.json').read_text())['vault_path'].endswith('Documents/Chassie-Memory')
    assert 'config set memory.provider chassie' in log.read_text()
    assert hermes_setup.connect(home, config, write_env) == key  # Again: same key, nothing duplicated.
    assert (home / '.env').read_text().count('API_SERVER_KEY') == 1
    (home / 'config.yaml').write_text(yaml.safe_dump({'memory': {'provider': 'chassie'}}))
    assert hermes_setup.status(home, config) == {'installed': True, 'connected': True}


def test_status_of_a_fresh_computer(tmp_path, monkeypatch):
    monkeypatch.setattr(hermes_setup, 'hermes_bin', lambda: None)
    assert hermes_setup.status(tmp_path, {'hermes': {'api_key_file': str(tmp_path / 'k')}}) == {'installed': False, 'connected': False}


def test_install_runs_unattended_stages_and_reports_failures(tmp_path, monkeypatch):
    script = tmp_path / 'install.sh'
    script.write_text("""case "$1" in
--manifest) echo '{"protocol_version":1,"stages":[{"name":"venv","title":"Create Python environment","needs_user_input":false},{"name":"setup","title":"Configure","needs_user_input":true},{"name":"products","title":"Install command","needs_user_input":false}]}';;
*) echo "$4" >> """ + str(tmp_path / 'ran') + """; if [ "$4" = products ] && [ -f """ + str(tmp_path / 'fail') + """ ]; then echo '{"ok":false,"stage":"products","skipped":false,"reason":"no git"}'; else echo '{"ok":true,"stage":"'$4'","skipped":false}'; fi;;
esac""")
    monkeypatch.setattr(hermes_setup, 'DATA', tmp_path)
    monkeypatch.setattr(hermes_setup.urllib.request, 'urlopen', lambda *a, **k: open(script, 'rb'))
    monkeypatch.setattr(hermes_setup, 'hermes_bin', lambda: '/bin/hermes')
    said = []
    hermes_setup.install(said.append)
    assert (tmp_path / 'ran').read_text().split() == ['venv', 'products']
    assert said == ['Installing Hermes, step 1 of 2: Create Python environment…', 'Installing Hermes, step 2 of 2: Install command…']
    (tmp_path / 'fail').touch()
    with pytest.raises(RuntimeError, match=r'Install command: no git\). You can also install it in a terminal'):
        hermes_setup.install(said.append)


@pytest.mark.asyncio
async def test_check_setup_says_what_is_missing_and_why(app, tmp_path, monkeypatch):
    import json as _json
    from brain import controls
    monkeypatch.setattr(controls, 'DATA', tmp_path)
    (tmp_path / '.chassie').mkdir()
    (tmp_path / '.chassie/first-run.json').write_text(_json.dumps({'running': False, 'at': 0, 'failed': {'speaker model': 'timed out'}}))
    monkeypatch.setattr(hermes_setup, 'status', lambda home, config: {'installed': True, 'connected': False})
    app._hermes.health_check = lambda: _ok(False)
    import speech.voice_identity as vi
    monkeypatch.setattr(vi, 'MODEL', tmp_path / 'missing.onnx')
    items = {i['name']: i for i in (await app.handle_control({'type': 'check_setup'}))['items']}
    assert items['Brain (Hermes)'] == {'name': 'Brain (Hermes)', 'ok': False, 'detail': 'Hermes is not connected to Chassie.', 'action': 'hermes_setup'}
    assert items['Voice recognition']['ok'] is False and items['Voice recognition']['detail'].endswith('Last try: timed out')


async def _ok(value):
    return value
