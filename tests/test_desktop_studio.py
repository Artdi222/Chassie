"""Native interaction regression, exercised on the supported Hyprland test desktop."""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest
from aiohttp import web
from test_orchestrator import app


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'), reason='Requires live Hyprland/XWayland')
@pytest.mark.requires_model
async def test_bubble_actions_stay_open_and_panels_are_above_avatar(app):
    runner=web.AppRunner(app._web_app)
    await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    endpoint=f'ws://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/ws'
    env={**os.environ,'QT_QPA_PLATFORM':'xcb'}
    process=None
    try:
        process=await asyncio.create_subprocess_exec(
            sys.executable,'tests/native_studio_probe.py',endpoint,env=env,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        output,_=await asyncio.wait_for(process.communicate(),40)
        Path('.test-artifacts').mkdir(exist_ok=True)
        Path('.test-artifacts/desktop-arc-check.log').write_bytes(output)
        assert process.returncode==0,output.decode(errors='replace')[-6000:]
        assert b'"transient_above_avatar": true' in output
        assert b'"compositor_gaps_transparent": true' in output
    finally:
        if process and process.returncode is None:
            process.kill();await process.wait()
        await runner.cleanup()


@pytest.mark.skipif(sys.platform!='linux' or importlib.util.find_spec('PySide6') is None or importlib.util.find_spec('live2d') is None,
                    reason='Requires Linux overlay dependencies')
def test_first_panel_opens_with_production_import_order(tmp_path):
    import subprocess
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen',
         'QTWEBENGINE_CHROMIUM_FLAGS':'--disable-gpu',
         'XDG_CACHE_HOME':str(tmp_path/'cache'),'XDG_DATA_HOME':str(tmp_path/'data')}
    result=subprocess.run([sys.executable,'tests/panel_startup_probe.py'],env=env,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
    assert result.returncode==0,result.stdout.decode(errors='replace')[-4000:]
    assert b'PANEL_READY 2' in result.stdout
