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
    expected = {'provider': 'anthropic', 'text_model': 'claude-haiku-5-5', 'vision_model': None, 'background_model': None, 'reasoning_effort': None}
    assert app.applied == expected and app._settings()['brain']['text_model'] == 'claude-haiku-5-5'
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text())['hermes'] == expected
    with pytest.raises(ValueError): await app.handle_control({'type': 'set_brain', 'text_model': 'bad model; rm'})
    with pytest.raises(ValueError, match='provider'): await app.handle_control({'type': 'set_brain', 'text_model': 'x'})
    with pytest.raises(ValueError, match='effort'): await app.handle_control({'type': 'set_brain', 'reasoning_effort': 'turbo'})
    await app.handle_control({'type': 'set_brain', 'provider': 'anthropic', 'reasoning_effort': 'low'})
    assert app.applied['reasoning_effort'] == 'low' and app._settings()['brain']['efforts'][0] == 'none'


@pytest.mark.asyncio
async def test_api_key_written_private_and_never_shown(app, tmp_path):
    env = tmp_path / '.env'; env.write_text('OTHER=1\nDEEPSEEK_API_KEY=old\n')
    app._hermes_env_path, app._local_config_root, app._hermes_home_path = env, tmp_path, tmp_path
    (tmp_path / 'models_dev_cache.json').write_text('{"deepseek": {"name": "DeepSeek", "env": ["DEEPSEEK_API_KEY"], "models": {}}}')
    app._hermes.set_models = lambda **kw: None
    with pytest.raises(ValueError, match='Hermes'): await app.handle_control({'type': 'set_api_key', 'key': 'sk-secret-123456'})
    await app.handle_control({'type': 'set_brain', 'provider': 'deepseek'})
    assert app._settings()['brain']['key_saved'] is True
    await app.handle_control({'type': 'set_api_key', 'key': 'sk-secret-123456'})
    assert env.read_text() == 'OTHER=1\nDEEPSEEK_API_KEY=sk-secret-123456\n' and oct(os.stat(env).st_mode & 0o777) == '0o600'
    assert 'sk-secret' not in str(app._settings())
    with pytest.raises(ValueError): await app.handle_control({'type': 'set_api_key', 'key': 'two\nlines-xxxxxxxx'})


@pytest.mark.asyncio
async def test_brain_test_reports_time_or_error(app):
    app._hermes.complete_once = AsyncMock(return_value='OK'); app._broadcast_settings = AsyncMock()
    result = await app.handle_control({'type': 'test_brain'})
    app._broadcast_settings.assert_awaited()  # Health panel refreshes after a test.
    assert result['type'] == 'brain_test' and result['ok'] and isinstance(result['seconds'], float)
    assert app._hermes.complete_once.call_args.kwargs == {'background': False}
    app._hermes.complete_once = AsyncMock(side_effect=RuntimeError('Hermes returned HTTP 401: invalid x-api-key'))
    result = await app.handle_control({'type': 'test_brain'})
    assert result == {'type': 'brain_test', 'ok': False, 'error': 'Hermes returned HTTP 401: invalid x-api-key'}


@pytest.mark.asyncio
async def test_provider_and_model_lists_come_from_hermes(app, tmp_path):
    from unittest.mock import patch
    (tmp_path / 'models_dev_cache.json').write_text('{"anthropic": {"name": "Anthropic", "env": ["ANTHROPIC_API_KEY"], "models": '
                                                     '{"claude-haiku-5-5": {"name": "Claude Haiku 5.5", "modalities": {"input": ["text", "image"]}}}}}')
    app._hermes_home_path = tmp_path
    with patch('brain.hermes_catalog.signed_in', return_value=['anthropic']):
        result = await app.handle_control({'type': 'list_providers'})
    assert result['providers'][0] == {'id': 'anthropic', 'label': 'Anthropic', 'signed_in': True, 'key_name': 'ANTHROPIC_API_KEY'}
    result = await app.handle_control({'type': 'list_models', 'provider': 'anthropic'})
    assert result == {'type': 'models', 'provider': 'anthropic', 'models': [{'id': 'claude-haiku-5-5', 'name': 'Claude Haiku 5.5', 'vision': True, 'reasoning': False}]}


@pytest.mark.asyncio
async def test_model_picker_lists_hermes_providers_and_models(app, tmp_path):
    from unittest.mock import patch
    from aiohttp import web
    from playwright.async_api import async_playwright
    (tmp_path / 'models_dev_cache.json').write_text('{"anthropic": {"name": "Anthropic", "env": ["ANTHROPIC_API_KEY"], "models": {'
        '"claude-haiku-5-5": {"name": "Claude Haiku 5.5", "modalities": {"input": ["text", "image"]}},'
        '"text-only": {"name": "Text Only", "modalities": {"input": ["text"]}}}}}')
    app._hermes_home_path, app._local_config_root = tmp_path, tmp_path
    app._hermes.set_models = lambda **kw: None
    app._config['hermes'] = {'provider': 'anthropic'}
    runner = web.AppRunner(app._web_app); await runner.setup(); site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    try:
        with patch('brain.hermes_catalog.signed_in', return_value=['anthropic']):
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(args=['--no-sandbox'])
                page = await browser.new_page(); errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                await page.goto(url + '/?panel=settings')
                await page.get_by_role('tab', name='System').click()
                await page.locator('#brain-provider').click()
                option = page.get_by_role('option', name='Anthropic Signed in')
                await option.wait_for()
                await page.screenshot(path='.test-artifacts/brain-provider-combo.png')
                await option.click()
                assert await page.locator('#brain-provider').input_value() == 'anthropic'
                await page.wait_for_function("document.getElementById('brain-models-note').textContent.includes('2 models')")
                await page.locator('#brain-vision_model').click()
                assert await page.locator('#brain-vision_model-options [role=option]').count() == 1  # Only models that read images.
                await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter')
                assert await page.locator('#brain-vision_model').input_value() == 'claude-haiku-5-5'
                await page.locator('#brain-text_model').fill('text')
                assert await page.locator('#brain-text_model-options [role=option]').count() == 1  # Search narrows the list.
                await page.keyboard.press('Escape')
                assert await page.locator('#brain-text_model-options').is_hidden()
                await page.get_by_role('button', name='Thinking effort').click()
                await page.get_by_role('option', name='Medium').wait_for()
                await page.locator('#brain-reasoning_effort-button').screenshot(path='.test-artifacts/effort-button.png')
                await page.evaluate("document.getElementById('brain-reasoning_effort-button').scrollIntoView({block: 'start'})")
                box = await page.locator('#brain-reasoning_effort-button').bounding_box()
                await page.screenshot(path='.test-artifacts/effort-open.png', clip={'x': 0, 'y': max(0, box['y'] - 30), 'width': 640, 'height': 360})
                await page.get_by_role('option', name='Medium').click()
                assert await page.locator('#brain-reasoning_effort-button').text_content() == 'Medium'
                await page.locator('#save-brain').click()
                await page.wait_for_timeout(300)
                assert app._config['hermes']['reasoning_effort'] == 'medium' and not errors
                await browser.close()
    finally:
        await runner.cleanup()
