import os
from unittest.mock import AsyncMock
import pytest
import yaml
from brain.hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG
from test_orchestrator import app  # noqa: F401


def test_bridge_models_follow_settings():
    bridge = HermesBridge(CONFIG)
    bridge.set_models(provider='deepseek', text_model='deepseek-chat', vision_model=None, background_model=None)
    assert bridge._request_payload([{'role': 'user', 'content': 'hi'}])['model'] == 'deepseek-chat'
    assert bridge._request_payload([], background=True)['provider'] == 'deepseek'
    assert bridge._vision_model == bridge._model  # None means Hermes's own default.


@pytest.mark.asyncio
async def test_set_brain_saves_and_applies(app, tmp_path):
    app._local_config_root = tmp_path
    app._hermes.set_models = lambda **kw: setattr(app, 'applied', kw)
    await app.handle_control({'type': 'set_brain', 'provider': 'anthropic', 'text_model': ' claude-haiku-5-5 ', 'vision_model': '', 'background_model': None})
    expected = {'provider': 'anthropic', 'text_model': 'claude-haiku-5-5', 'vision_model': None, 'background_model': None}
    assert app.applied == expected and app._settings()['brain']['text_model'] == 'claude-haiku-5-5'
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text())['hermes'] == expected
    with pytest.raises(ValueError): await app.handle_control({'type': 'set_brain', 'text_model': 'bad model; rm'})
    with pytest.raises(ValueError, match='provider'): await app.handle_control({'type': 'set_brain', 'text_model': 'x'})


@pytest.mark.asyncio
async def test_api_key_written_private_and_never_shown(app, tmp_path):
    env = tmp_path / '.env'; env.write_text('OTHER=1\nDEEPSEEK_API_KEY=old\n')
    app._hermes_env_path, app._local_config_root = env, tmp_path
    app._hermes.set_models = lambda **kw: None
    with pytest.raises(ValueError, match='provider'): await app.handle_control({'type': 'set_api_key', 'key': 'sk-secret-123456'})
    await app.handle_control({'type': 'set_brain', 'provider': 'deepseek'})
    assert app._settings()['brain']['key_saved'] is True
    await app.handle_control({'type': 'set_api_key', 'key': 'sk-secret-123456'})
    assert env.read_text() == 'OTHER=1\nDEEPSEEK_API_KEY=sk-secret-123456\n' and oct(os.stat(env).st_mode & 0o777) == '0o600'
    assert 'sk-secret' not in str(app._settings())
    with pytest.raises(ValueError): await app.handle_control({'type': 'set_api_key', 'key': 'two\nlines-xxxxxxxx'})


@pytest.mark.asyncio
async def test_brain_test_reports_time_or_error(app):
    app._hermes.complete_once = AsyncMock(return_value='OK')
    result = await app.handle_control({'type': 'test_brain'})
    assert result['type'] == 'brain_test' and result['ok'] and isinstance(result['seconds'], float)
    assert app._hermes.complete_once.call_args.kwargs == {'background': False}
    app._hermes.complete_once = AsyncMock(side_effect=RuntimeError('Hermes returned HTTP 401: invalid x-api-key'))
    result = await app.handle_control({'type': 'test_brain'})
    assert result == {'type': 'brain_test', 'ok': False, 'error': 'Hermes returned HTTP 401: invalid x-api-key'}
