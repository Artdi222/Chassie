from pathlib import Path
from unittest.mock import Mock,AsyncMock
import pytest
from aiohttp import web
from playwright.async_api import async_playwright
from tts_engine import TTSEngine
from style_bert_tts import ExpressiveTTS
from test_orchestrator import app


@pytest.mark.asyncio
async def test_speech_selector_persists_and_shows_voicevox_without_loading_models(app,tmp_path):
    config={**app._config,'tts':{'engine':'style_bert','sample_rate':24000,'selection_path':str(tmp_path/'speech.json')}}
    app._config=config
    engine=TTSEngine(config)
    primary=Mock(ready=True,warmup=AsyncMock(),synthesize=AsyncMock(),close=AsyncMock())
    voicevox=Mock(synthesize=AsyncMock(),close=AsyncMock())
    engine._expressive=ExpressiveTTS(config,primary=primary,voicevox=voicevox);engine._ready=True
    app._tts=engine
    runner=web.AppRunner(app._web_app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':460,'height':900});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto(f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/?panel=settings')
            await page.locator('#speech-engine').wait_for(state='visible')
            assert await page.locator('#speech-engine').input_value()=='style_bert'
            assert await page.locator('#ami-credit').is_visible()
            assert await page.locator('#speech-credit').is_visible()
            await page.locator('#speech-engine').select_option('voicevox')
            await page.get_by_text('VOICEVOX selected',exact=True).wait_for()
            primary.close.assert_awaited_once()
            assert (tmp_path/'speech.json').exists()
            await page.reload();await page.get_by_text('VOICEVOX selected',exact=True).wait_for()
            await page.locator('#speech-engine').select_option('style_bert')
            await page.wait_for_function("document.getElementById('speech-status').textContent.includes('Ami ready')")
            engine._expressive.reason='slow';engine._expressive.active=None
            await app._broadcast_to_ui({'type':'speech_status',**engine.status()})
            await page.get_by_text('Ami took too long · text is still available',exact=True).wait_for()
            assert await page.locator('#speech-engine').input_value()=='style_bert'
            voicevox.synthesize.assert_not_awaited()
            out=Path('.test-artifacts/speech');out.mkdir(parents=True,exist_ok=True)
            await page.screenshot(path=str(out/'selector-manual.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors
            await browser.close()
    finally:await engine.close();await runner.cleanup()
