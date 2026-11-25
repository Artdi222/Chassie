from pathlib import Path
from unittest.mock import Mock
import pytest
from aiohttp import web
from playwright.async_api import async_playwright
from speech.voice_identity import VoiceIdentity
from test_orchestrator import app


@pytest.mark.asyncio
async def test_simplified_memory_consent_and_chat_scroll_copy_retry(app):
    app._automatic_memory=True
    owner=app._memory.create_profile('Synthetic owner',consent=True);app._session_context.set_owner(owner.id)
    app._speaker=VoiceIdentity(app._memory)
    status={'camera':{'enabled':True,'available':True,'error':None},'screen':{'enabled':False,'available':False,'error':None},
            'identity':{'face_count':1,'matches':[],'error':None,'ready':True}}
    app._vision=Mock(status=Mock(return_value=status),enrollment=Mock(return_value=[.1]*512))
    app._vault=Mock(status=Mock(return_value={'available':True,'path':'/synthetic/Memory','chunks':2,'pending_cloud_sources':0}),
                    list=Mock(return_value=[{'id':'note','content':'A handwritten workspace note','source':'workspace.md','editable':False}]))
    runner=web.AppRunner(app._web_app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    artifacts=Path('.test-artifacts/memory-chat');artifacts.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(args=['--no-sandbox'])
            context=await browser.new_context(viewport={'width':440,'height':900},permissions=['clipboard-read','clipboard-write'])
            page=await context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' and 'parsing WebSocket' in msg.text else None)
            await page.goto(url+'/?panel=settings')
            await page.get_by_role('tab',name='People & memory').click()
            await page.get_by_text('Your memories are active.',exact=True).wait_for()
            await page.wait_for_function("document.getElementById('vault-state').textContent.includes('/synthetic/Memory')")
            assert not await page.locator('#profile-select').is_visible()
            assert not await page.locator('#guest-form').is_visible()
            await page.get_by_text('Introduce someone',exact=True).click()
            await page.locator('#person-name').fill('Synthetic friend')
            await page.get_by_role('button',name='Remember with permission').click()
            assert not app._memory.list_faces()
            await page.locator('#person-consent').check()
            await page.get_by_role('button',name='Remember with permission').click()
            await page.get_by_text('Synthetic friend · Face remembered',exact=True).wait_for()
            assert not await page.locator('#person-consent').is_checked()
            assert app._session_context.owner_profile_id==owner.id
            await page.get_by_text('Saved memories',exact=True).click()
            await page.locator('#load-memories').click()
            await page.get_by_text('A handwritten workspace note',exact=True).wait_for()
            assert await page.locator('#memory-list button').count()==0
            await page.screenshot(path=str(artifacts/'memory-settings.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.goto(url+'/?panel=chat')
            await page.wait_for_function("!document.getElementById('mic-toggle').disabled")
            items=[{'role':'user' if i%2 else 'assistant','text':f'Message {i}. '+('Long enough to scroll. '*6)} for i in range(30)]
            await app._broadcast_to_ui({'type':'history_snapshot','items':items})
            await page.wait_for_function("document.querySelectorAll('.message-bubble').length===30")
            messages=page.locator('#messages-container')
            await messages.evaluate('(el)=>el.scrollTop=150')
            await page.wait_for_timeout(100)
            top=await messages.evaluate('(el)=>el.scrollTop')
            for text in ('[happy] First line.','[happy] First line. Second line. Third line.'):
                await app._broadcast_to_ui({'type':'chat_stream','id':'synthetic-stream','text':text,'done':False})
                await page.wait_for_timeout(80)
                assert abs(await messages.evaluate('(el)=>el.scrollTop')-top)<2
            await page.locator('#jump-latest').click()
            assert await messages.evaluate('(el)=>el.scrollHeight-el.clientHeight-el.scrollTop<3')
            copy=page.locator('[data-stream-id="synthetic-stream"] .copy-message')
            await copy.click()
            assert await page.evaluate('navigator.clipboard.readText()')=='First line. Second line. Third line.'
            await app._broadcast_to_ui({'type':'notice','scope':'chat','text':'Synthetic request failed.','retry_text':'The original question?'})
            await page.get_by_role('button',name='Try again',exact=True).click()
            await page.wait_for_timeout(100)
            assert (await app._ui_input_queue.get())['text']=='The original question?'
            await page.screenshot(path=str(artifacts/'chat-actions.png'))
            assert not errors,errors
            await browser.close()
    finally:await runner.cleanup()
