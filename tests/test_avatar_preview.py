import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientSession, web
from orchestrator import Orchestrator


@pytest.fixture
def app(tmp_path):
    stt = Mock(error=None, is_listening=Mock(return_value=False))
    config = {'audio': {'output_sample_rate': 24000}, 'companion': {'memory_path': str(tmp_path / 'memory.sqlite')}}
    if (Path(__file__).resolve().parents[1] / 'model/Model_4').is_dir():
        (tmp_path / 'model-selection.json').write_text('{"model_id":"Model_4"}')
    result = Orchestrator(config, text_mode=True, components={
        'stt': stt, 'hermes': Mock(get_history=Mock(return_value=[])),
        'tts': Mock(), 'player': Mock(), 'analyzer': Mock()})
    yield result
    result._memory.close()


def registration(ready=True, model_id='Model_4'):
    return {'type': 'overlay_ready', 'ready': ready, 'model_id': model_id, 'expressions': []}


@pytest.mark.asyncio
async def test_no_renderer_does_not_advertise_or_accept_preview(app):
    inventory = await app.handle_control({'type': 'avatar_inventory'})
    assert not inventory['capabilities']['emotions']['happy']['available']
    with pytest.raises(ValueError, match='renderer'):
        await app.handle_control({'type': 'preview_emotion', 'emotion': 'happy'})


@pytest.mark.asyncio
@pytest.mark.requires_model
async def test_overlay_ready_tracks_model_without_expression_files(app):
    socket = Mock(closed=False, send_json=AsyncMock())
    app._ui_sockets.add(socket)
    await app._register_overlay(socket, registration())
    inventory = app._avatar_capabilities()
    assert inventory['overlay_ready']
    # Tian Muzi reacts through generated parameters, never expression files.
    assert not inventory['emotions']['happy']['available']
    await app._register_overlay(socket, registration(False))
    assert not app._avatar_capabilities()['overlay_ready']


@pytest.mark.asyncio
async def test_wrong_model_and_unknown_socket_are_rejected(app):
    socket = Mock(closed=False, send_json=AsyncMock())
    app._ui_sockets.add(socket)
    with pytest.raises(ValueError): await app._register_overlay(socket, registration(model_id='other'))
    assert not app._avatar_capabilities()['overlay_ready']
    with pytest.raises(ValueError):
        await app.handle_control({'type': 'overlay_ready', **registration()})


async def receive_type(ws, kind):
    async with asyncio.timeout(2):
        while True:
            data = await ws.receive_json()
            if data.get('type') == kind:
                return data


@pytest.mark.asyncio
@pytest.mark.requires_model
async def test_actual_websocket_registration_and_disconnect(app):
    runner = web.AppRunner(app._web_app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as client:
            browser = await client.ws_connect(f'http://127.0.0.1:{port}/ws')
            overlay = await client.ws_connect(f'http://127.0.0.1:{port}/ws')
            await overlay.send_json(registration())
            async with asyncio.timeout(2):
                while not (await receive_type(browser, 'avatar_inventory'))['capabilities']['overlay_ready']:
                    pass
            await overlay.close()
            async with asyncio.timeout(2):
                while (await receive_type(browser, 'avatar_inventory'))['capabilities']['overlay_ready']:
                    pass
            await browser.close()
    finally:
        await runner.cleanup()
