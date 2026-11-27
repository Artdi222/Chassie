import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from avatar.appearance import AppearanceCache, fingerprint
from brain.hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG
from test_orchestrator import app  # noqa: F401


def fake_entry(tmp_path):
    for name in ('m.model3.json', 'm.moc3', 'tex.png', 'motion.json'): (tmp_path / name).write_text(name)
    return SimpleNamespace(id='m', path=tmp_path / 'm.model3.json', root=tmp_path,
                           data={'FileReferences': {'Moc': 'm.moc3', 'Textures': ['tex.png']}})


def test_fingerprint_follows_the_design_files_only(tmp_path):
    entry = fake_entry(tmp_path)
    first = fingerprint(entry)
    (tmp_path / 'motion.json').write_text('a new motion')
    assert fingerprint(entry) == first  # Motions do not change how she looks.
    (tmp_path / 'tex.png').write_text('repainted texture')
    assert fingerprint(entry) != first


def test_cache_returns_only_the_matching_design(tmp_path):
    cache = AppearanceCache(tmp_path / 'appearance.json')
    cache.put('a', 'f1', 'I have blue hair.'); cache.put('b', 'f9', 'I have blond hair.')
    assert cache.get('a', 'f1') == 'I have blue hair.' and cache.get('a', 'f2') is None and cache.get('b', 'f9') == 'I have blond hair.'
    cache.forget('a')
    assert cache.get('a', 'f1') is None and json.loads((tmp_path / 'appearance.json').read_text())['b']['text'] == 'I have blond hair.'


def test_prompt_carries_current_look():
    bridge = HermesBridge(CONFIG)
    assert 'current look' not in bridge._system_prompt('focus')
    bridge.appearance = 'I have long blue hair.'
    assert 'I have long blue hair.' in bridge._system_prompt('casual') and 'overrides' in bridge._system_prompt('focus')


@pytest.mark.asyncio
async def test_snapshot_is_described_once_per_design(app, tmp_path):
    entry = fake_entry(tmp_path)
    app._catalog = SimpleNamespace(get=lambda model_id: entry, models={'m': entry})
    app._model_selection = SimpleNamespace(state={'model_id': 'm'})
    app._appearance = AppearanceCache(tmp_path / 'appearance.json')
    app._broadcast_to_ui = AsyncMock(); app._broadcast_settings = AsyncMock()
    app._hermes.appearance = ''
    app._hermes.complete_once = AsyncMock(return_value='  I have long blue hair and glasses.  ')
    await app._sync_appearance()
    app._broadcast_to_ui.assert_awaited_once_with({'type': 'appearance_needed', 'model_id': 'm'})
    with pytest.raises(ValueError): await app.handle_control({'type': 'avatar_snapshot', 'model_id': 'other', 'image': 'data:image/png;base64,AA'})
    await app.handle_control({'type': 'avatar_snapshot', 'model_id': 'm', 'image': 'data:image/png;base64,AA'})
    await app._appearance_task
    assert app._hermes.complete_once.call_args.kwargs['images'] == ['data:image/png;base64,AA']
    assert app._hermes.appearance == 'I have long blue hair and glasses.' and app._settings()['appearance']['text'] == app._hermes.appearance
    app._broadcast_to_ui.reset_mock(); app._hermes.complete_once.reset_mock()
    await app._sync_appearance()  # Same design again (or switching back to it): no new request.
    app._broadcast_to_ui.assert_not_awaited(); app._hermes.complete_once.assert_not_awaited()
    (tmp_path / 'tex.png').write_text('updated design'); os.utime(tmp_path / 'tex.png', None)
    await app._sync_appearance()
    app._broadcast_to_ui.assert_awaited_once_with({'type': 'appearance_needed', 'model_id': 'm'})
    assert app._hermes.appearance == ''  # The old description no longer fits.


def test_avatar_png_crops_to_the_drawn_part():
    import base64
    from PySide6.QtGui import QColor, QImage
    from desktop.snapshot import avatar_png
    image = QImage(400, 300, QImage.Format.Format_RGBA8888); image.fill(QColor(0, 0, 0, 0))
    assert avatar_png(image) is None  # Nothing drawn yet.
    for x in range(100, 150):
        for y in range(50, 250): image.setPixelColor(x, y, QColor(20, 40, 200, 255))
    png = QImage.fromData(base64.b64decode(avatar_png(image)), 'PNG')
    assert (png.width(), png.height()) == (50, 200)


@pytest.mark.asyncio
async def test_avatar_picture_does_not_close_the_socket(app):
    import aiohttp
    from aiohttp import web
    runner = web.AppRunner(app._web_app); await runner.setup(); site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/ws'
    try:
        async with aiohttp.ClientSession() as session, session.ws_connect(url) as ws:
            picture = 'data:image/png;base64,' + 'A' * 200_000  # A real avatar picture is ~150-250 KB.
            await ws.send_json({'type': 'avatar_snapshot', 'model_id': 'not-the-current-one', 'image': picture})
            while True:  # Skip the hydration messages; the answer is a notice, not a closed socket.
                reply = await ws.receive_json(timeout=5)
                if reply.get('type') == 'notice': break
            assert 'avatar changed' in reply['text'] and not ws.closed
    finally:
        await runner.cleanup()
