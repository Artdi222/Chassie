from pathlib import Path

from aiohttp import web
import pytest
from playwright.async_api import async_playwright

from test_orchestrator import app  # noqa: F401  (fixture)


@pytest.mark.asyncio
async def test_web_avatar_follows_face_and_tilts_while_thinking(app):
    app._model_selection.change({'model_id': 'Model_4'}, persist=False)
    runner = web.AppRunner(app._web_app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    artifacts = Path('.test-artifacts/web-presence'); artifacts.mkdir(parents=True, exist_ok=True)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox', '--enable-unsafe-swiftshader'])
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await page.wait_for_function('window.modelStudio?.ready', timeout=45000)
            await page.mouse.move(5, 5)
            # Face on the camera image's right and low: she looks to the viewer's left and down.
            await page.evaluate('''() => window.dispatchEvent(new CustomEvent('chassie-message', {detail:
                {type:'avatar_state', emotion:'neutral', mouth:0, generation:1, status:'thinking', gaze:[0.8, 0.6]}}))''')
            await page.wait_for_function('''() => {
                const f = window.modelStudio.pointerController.avatar.internalModel.focusController;
                return f.x < -.3 && f.y < -.15;
            }''', timeout=5000)
            await page.wait_for_timeout(1500)
            # Cubism restores its baseline after drawing; read the offset applied each frame.
            tilt = await page.evaluate('window.modelStudio.headMotion.current.ParamAngleZ')
            await page.screenshot(path=str(artifacts / 'thinking-looking.png'))
            assert tilt < -2  # Thinking tilt applied on top of the model's own motion.
            # The real parameter each frame must stay bounded (no frame-to-frame accumulation).
            await page.evaluate('''() => window.dispatchEvent(new CustomEvent('chassie-message', {detail:
                {type:'avatar_state', emotion:'neutral', mouth:0, generation:2, status:'idle', gaze:null}}))''')
            angles = await page.evaluate('''() => new Promise(done => {
                const m = window.modelStudio.pointerController.avatar.internalModel, seen = [];
                const probe = () => seen.push(m.coreModel.getParameterValueById('ParamAngleZ'));
                m.on('beforeModelUpdate', probe);
                setTimeout(() => { m.off('beforeModelUpdate', probe); done(seen); }, 2500);
            })''')
            assert len(angles) > 20 and max(abs(a) for a in angles[-15:]) < 8, angles[-15:]
            assert not errors
            await browser.close()
    finally:
        await runner.cleanup()
