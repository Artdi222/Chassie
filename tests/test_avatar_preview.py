import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientSession, web
from avatar import load_manifest
from orchestrator import Orchestrator


@pytest.fixture
def app(tmp_path):
    vts = Mock(is_authenticated=False, last_error='VTS unavailable', preview_emotion=AsyncMock(return_value=False))
    vts.get_capabilities.return_value = {'emotions': {}}
    stt = Mock(error=None, is_listening=Mock(return_value=False))
    config = {'audio': {'output_sample_rate': 24000}, 'companion': {'memory_path': str(tmp_path / 'memory.sqlite')}}
    result = Orchestrator(config, text_mode=True, components={
        'vts': vts, 'stt': stt, 'hermes': Mock(get_history=Mock(return_value=[])),
        'tts': Mock(), 'player': Mock(), 'analyzer': Mock()})
    yield result
    result._memory.close()


def registration(ready=True):
    manifest = load_manifest()
    return {'type': 'overlay_ready', 'ready': ready, 'model_id': manifest.model_id,
            'expressions': sorted(manifest.managed_files)}


@pytest.mark.asyncio
async def test_no_renderer_does_not_advertise_or_accept_preview(app):
    inventory = await app.handle_control({'type': 'avatar_inventory'})
    assert not inventory['capabilities']['emotions']['happy']['available']
    with pytest.raises(ValueError, match='renderer'):
        await app.handle_control({'type': 'preview_emotion', 'emotion': 'happy'})


@pytest.mark.asyncio
async def test_overlay_ready_enables_preview_without_vts_and_drop_disables(app):
    socket = Mock(closed=False, send_json=AsyncMock())
    app._ui_sockets.add(socket)
    await app._register_overlay(socket, registration())
    inventory = app._avatar_capabilities()
    assert inventory['emotions']['happy']['available']
    assert inventory['emotions']['happy']['backends'] == ['overlay']
    await app.handle_control({'type': 'preview_emotion', 'emotion': 'happy'})
    assert app._avatar_state['emotion'] == 'happy'
    app._vts.preview_emotion.assert_not_awaited()
    await app._register_overlay(socket, registration(False))
    assert not app._avatar_capabilities()['emotions']['happy']['available']


@pytest.mark.asyncio
async def test_unready_wrong_model_and_missing_assets_never_advertise(app):
    socket = Mock(closed=False, send_json=AsyncMock())
    app._ui_sockets.add(socket)
    await app._register_overlay(socket, registration(False))
    assert not app._avatar_capabilities()['overlay_ready']
    bad = registration(); bad['model_id'] = 'other'
    with pytest.raises(ValueError): await app._register_overlay(socket, bad)
    incomplete = registration(); incomplete['expressions'].remove('smile.exp3.json')
    await app._register_overlay(socket, incomplete)
    assert not app._avatar_capabilities()['emotions']['happy']['available']
    assert app._avatar_capabilities()['emotions']['shy']['available']
    with pytest.raises(ValueError):
        await app.handle_control({'type': 'overlay_ready', **registration()})


@pytest.mark.asyncio
async def test_failed_vts_does_not_block_ready_overlay(app):
    socket = Mock(closed=False, send_json=AsyncMock())
    app._ui_sockets.add(socket)
    await app._register_overlay(socket, registration())
    app._vts.get_capabilities.return_value = {'emotions': {'happy': {'available': True}}}
    await app.handle_control({'type': 'preview_emotion', 'emotion': 'happy'})
    app._vts.preview_emotion.assert_awaited_once_with('happy')
    assert app._avatar_state['emotion'] == 'happy'


async def receive_type(ws, kind):
    async with asyncio.timeout(2):
        while True:
            data = await ws.receive_json()
            if data.get('type') == kind:
                return data


@pytest.mark.asyncio
async def test_actual_websocket_registration_disconnect_and_preview(app):
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
            await browser.send_json({'type': 'preview_emotion', 'emotion': 'shy'})
            async with asyncio.timeout(2):
                while (await receive_type(overlay, 'avatar_state'))['emotion'] != 'shy':
                    pass
            await overlay.close()
            async with asyncio.timeout(2):
                while (await receive_type(browser, 'avatar_inventory'))['capabilities']['overlay_ready']:
                    pass
            await browser.close()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_catalog_overlay_readiness_tracks_switch_without_reusing_original_expressions(app):
    socket=Mock(closed=False,send_json=AsyncMock());app._ui_sockets.add(socket)
    await app._register_overlay(socket,{'ready':True,'model_id':'Model_1','expressions':['animation/'+f for f in load_manifest().managed_files]})
    assert app._avatar_capabilities()['emotions']['happy']['available']
    await app.handle_control({'type':'select_model','model_id':'Model_4'})
    assert not app._avatar_capabilities()['overlay_ready']
    await app._register_overlay(socket,{'ready':True,'model_id':'Model_4','expressions':[]})
    assert app._avatar_capabilities()['overlay_ready']
    assert not app._avatar_capabilities()['emotions']['happy']['available']
