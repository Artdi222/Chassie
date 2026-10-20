import asyncio
from pathlib import Path

from aiohttp import ClientSession, web
import pytest
from playwright.async_api import async_playwright

from test_orchestrator import app
from hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG


@pytest.mark.asyncio
async def test_automatic_vision_status_without_activation_buttons(app):
    from unittest.mock import Mock
    status={'camera':{'enabled':True,'available':True,'error':None},
            'screen':{'enabled':True,'available':True,'error':None},
            'identity':{'face_count':1,'matches':[{'name':'Synthetic owner'}],'error':None}}
    app._vision=Mock(status=Mock(return_value=status))
    runner=web.AppRunner(app._web_app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    artifacts=Path('.impeccable/review');artifacts.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':520,'height':900})
            await page.goto(f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/?panel=settings')
            await page.get_by_role('tab',name='System').click()
            await page.get_by_text('Camera active · Screen active',exact=True).wait_for()
            assert await page.get_by_text('Face match: Synthetic owner. Recognition is an estimate.',exact=True).is_visible()
            assert await page.get_by_role('button',name='Start camera').count()==0
            await page.screenshot(path=str(artifacts/'desktop.png'))
            await page.set_viewport_size({'width':390,'height':844})
            await page.screenshot(path=str(artifacts/'mobile.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            failed={**status,'screen':{'enabled':True,'available':False,'error':'Screen unavailable. Check desktop capture access.'}}
            await app._broadcast_to_ui({'type':'vision_status',**failed})
            await page.wait_for_function('document.getElementById("vision-state").textContent.includes("Screen unavailable")')
            await browser.close()
    finally:
        await runner.cleanup()

@pytest.mark.asyncio
async def test_http_gateway_and_clear_revision():
    entered=asyncio.Event();release=asyncio.Event();seen=[]
    async def reply(request):
        seen.append(await request.json());entered.set();await release.wait()
        return web.json_response({'choices':[{'message':{'content':'[neutral] Hello.'}}]})
    server=web.Application();server.router.add_post('/v1/chat/completions',reply)
    runner=web.AppRunner(server);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    config={**CONFIG,'hermes':{**CONFIG['hermes'],'gateway_url':f'http://127.0.0.1:{port}','reasoning_effort':'low'}}
    h=HermesBridge(config);await h.connect()
    try:
        task=asyncio.create_task(h.send_message('synthetic test'))
        await asyncio.wait_for(entered.wait(),1);h.clear_history();release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert seen[0]['messages'][-1]['content']=='synthetic test'
        assert seen[0]['model_options']=={'reasoning_effort':'low'}
        assert len(h.get_history())==1
    finally: await h.close();await runner.cleanup()

@pytest.mark.asyncio
async def test_browser_controls_and_guest_privacy(app):
    runner=web.AppRunner(app._web_app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1];url=f'http://127.0.0.1:{port}'
    artifacts=Path('.test-artifacts');artifacts.mkdir(exist_ok=True)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            page.set_default_timeout(8000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(url)
            await page.locator('#menu-toggle').click()
            await page.locator('#mic-toggle').wait_for(state='attached')
            await page.wait_for_function('!document.getElementById("mic-toggle").disabled')
            await page.locator('.setting-row .switch').click()
            await page.wait_for_function('document.getElementById("voice-state").textContent === "Microphone muted"')
            assert app._stt.muted
            await page.locator('#input-mode').select_option('hands_free')
            await page.wait_for_function('document.getElementById("input-mode").value === "hands_free"')
            await page.get_by_role('tab',name='People & memory').click()
            await page.locator('#profile-name').fill('Synthetic owner')
            await page.locator('#profile-consent').check()
            await page.locator('#profile-form button').click()
            await page.wait_for_function('document.getElementById("profile-select").value !== ""')
            await page.get_by_text('Saved memories',exact=True).click()
            await page.locator('#memory-content').fill('Synthetic secret preference')
            await page.locator('#memory-consent').check()
            await page.locator('#memory-form button').click()
            await page.locator('#load-memories').click()
            await page.get_by_text('Synthetic secret preference',exact=True).wait_for()
            await page.locator('#guest-name').fill('Synthetic guest')
            await page.locator('#guest-form button').click()
            await page.wait_for_function('document.getElementById("session-scope").textContent.includes("Shared")')
            assert await page.locator('#memory-list').inner_text()==''
            assert 'Synthetic secret preference' not in app._context_text()
            # Update one partial bubble, preserve unknown bracket text, hydrate
            # reconnect state without duplicates, and retain an interrupted label.
            await app._broadcast_to_ui({'type':'chat_stream','id':'stream-test','text':'[hap','done':False})
            await app._broadcast_to_ui({'type':'chat_stream','id':'stream-test','text':'[happy] First sentence.','done':False})
            await page.get_by_text('First sentence.',exact=True).wait_for()
            await app._broadcast_to_ui({'type':'history_snapshot','items':[{'role':'assistant','text':'[happy] First sentence.','stream_id':'stream-test'}]})
            await app._broadcast_to_ui({'type':'chat_stream','id':'stream-test','text':'[happy] First sentence. Keep [array] literal.','done':True,'interrupted':True})
            await page.get_by_text('First sentence. Keep [array] literal.',exact=True).wait_for()
            assert await page.locator('.message-bubble.assistant').count()==1
            assert await page.locator('.message-bubble.assistant .bubble-meta').inner_text()=='Chassie • Interrupted'
            await app._broadcast_to_ui({'type':'history_cleared'})
            await page.get_by_text('Conversation history cleared.',exact=True).wait_for()
            assert await page.locator('.message-bubble.assistant').count()==0
            await page.screenshot(path=str(artifacts/'controls-desktop.png'),full_page=True)
            await page.locator('#sidebar-close').click()
            await page.set_viewport_size({'width':390,'height':844})
            # A turn failure must remain visible when mobile hides the sidebar.
            await app._broadcast_to_ui({'type':'notice','scope':'chat','stream_id':'failed-turn',
                                       'text':'Hermes streaming request timed out. Please retry.'})
            alert=page.locator('#messages-container [role="alert"]').filter(has_text='timed out')
            await alert.wait_for(state='visible')
            assert await alert.count()==1
            assert await page.locator('.message-bubble.assistant').count()==0
            await page.screenshot(path=str(artifacts/'chat-timeout-mobile.png'),full_page=True)
            await page.locator('#menu-toggle').click()
            await page.wait_for_function('document.querySelector(".sidebar").getBoundingClientRect().left >= -1')
            await page.locator('#guest-name').scroll_into_view_if_needed()
            await page.screenshot(path=str(artifacts/'controls-mobile.png'),full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors,errors
            await browser.close()
        async with ClientSession() as client:
            response=await client.get(url+'/ws',headers={'Origin':'https://unrelated.example'})
            assert response.status==403
            response=await client.get(url+'/ws',headers={'Host':'attacker.example','Origin':'http://attacker.example'})
            assert response.status==403
    finally: await runner.cleanup()
