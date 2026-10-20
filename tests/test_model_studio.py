import asyncio
from pathlib import Path

from aiohttp import web
import pytest
from playwright.async_api import async_playwright

from test_orchestrator import app


@pytest.mark.asyncio
async def test_model_four_pointer_chat_and_controls(app):
    app._model_selection.change({'model_id':'Model_4'},persist=False)
    runner=web.AppRunner(app._web_app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    artifacts=Path('.test-artifacts/model-studio');artifacts.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(args=['--no-sandbox','--enable-unsafe-swiftshader'])
            page=await browser.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto(url)
            for model_id in ['Model_4']:
                await page.locator('#open-models').click()
                await page.locator(f'[data-model-id="{model_id}"]').click()
                await page.wait_for_function('(id)=>window.modelStudio?.ready && window.modelStudio.modelId===id',arg=model_id,timeout=45000)
                await page.locator('#close-models').click()
                await page.wait_for_timeout(400)
                head=await page.evaluate('''() => {
                    const c=window.modelStudio.pointerController,internal=c.avatar.internalModel;
                    let l=Infinity,r=-Infinity,t=Infinity,b=-Infinity;
                    for(const i of c.headDrawables){if(internal.coreModel.getDrawableOpacity(i)<=.01)continue;const v=internal.getDrawableBounds(i);l=Math.min(l,v.x);r=Math.max(r,v.x+v.width);t=Math.min(t,v.y);b=Math.max(b,v.y+v.height);}
                    const point=internal.localTransform.apply(new PIXI.Point((l+r)/2,(t+b)/2));
                    c.avatar.transform.worldTransform.apply(point,point);const box=c.canvas.getBoundingClientRect();
                    return {x:box.left+point.x,y:box.top+point.y,count:c.headDrawables.length};
                }''')
                assert head['count']>0,model_id
                await page.mouse.move(head['x'],head['y'])
                await page.wait_for_function('window.modelStudio.pointer?.amount>.95',timeout=4000)
                # Cubism restores its parameter baseline after drawing. The
                # rendered state is tested by the headpat amount and screenshot.
                assert await page.evaluate('window.modelStudio.pointer.headpat')
                await page.screenshot(path=str(artifacts/f'{model_id}-headpat.png'))
                edge=await page.evaluate('''() => {
                    const c=window.modelStudio.pointerController,b=c.bounds;
                    const p=c.avatar.internalModel.localTransform.apply(new PIXI.Point((b.left+b.right)/2,b.top));
                    c.avatar.transform.worldTransform.apply(p,p);const r=c.canvas.getBoundingClientRect();
                    return {x:r.left+p.x,y:r.top+p.y};
                }''')
                # Hover just above the hair while its mesh moves with the nod.
                # Crossing the entry edge must stay inside the wider exit area.
                for offset in (-18,-6,-20,-8):
                    await page.mouse.move(edge['x'],edge['y']+offset)
                    await page.wait_for_timeout(220)
                    assert await page.evaluate('window.modelStudio.pointer.headpat && window.modelStudio.pointer.amount>.95'),model_id
                await page.mouse.move(10,10)
                await page.wait_for_function('window.modelStudio.pointer?.amount<.01',timeout=4000)
                await page.wait_for_function('''() => {
                    const f=window.modelStudio.pointerController.avatar.internalModel.focusController;
                    return Math.abs(f.x)<.02 && Math.abs(f.y)<.02;
                }''',timeout=4000)
                canvas=await page.locator('#avatar-canvas').bounding_box()
                # Nearby hair, outside headpat contact: look at the cursor.
                # Re-measure after returning from the nod to the neutral pose.
                side=await page.evaluate('''() => {
                    const c=window.modelStudio.pointerController,m=c.avatar.internalModel;
                    const boxes=c.headDrawables.filter(i=>m.coreModel.getDrawableOpacity(i)>.01).map(i=>m.getDrawableBounds(i));
                    const left=Math.min(...boxes.map(b=>b.x)),top=Math.min(...boxes.map(b=>b.y)),bottom=Math.max(...boxes.map(b=>b.y+b.height));
                    const p=m.localTransform.apply(new PIXI.Point(left,(top+bottom)/2));
                    c.avatar.transform.worldTransform.apply(p,p);const r=c.canvas.getBoundingClientRect();
                    return {x:r.left+p.x-140,y:r.top+p.y};
                }''')
                await page.mouse.move(side['x'],side['y'])
                await page.wait_for_function('''() => {
                    const s=window.modelStudio,f=s.pointerController.avatar.internalModel.focusController;
                    return s.pointer.tracking && !s.pointer.headpat && f.x<-.1;
                }''',timeout=4000)
                # One pixel beyond the proximity halo must still restore idle.
                await page.mouse.move(canvas['x']+canvas['width']+181,canvas['y']+canvas['height']/2)
                await page.wait_for_function('''() => {
                    const s=window.modelStudio,f=s.pointerController.avatar.internalModel.focusController;
                    return !s.pointer.tracking && Math.abs(f.x)<.02 && Math.abs(f.y)<.02;
                }''',timeout=4000)
                await page.mouse.move(10,10)
                await page.screenshot(path=str(artifacts/f'{model_id}.png'))
                assert await page.locator('#avatar-canvas').is_visible()
            await page.locator('#open-models').click()
            assert await page.locator('[data-model-id="Model_3"]').count()==0
            assert await page.locator('#model-panel').get_attribute('role')=='dialog'
            await page.locator('#auto-expression').uncheck()
            await page.wait_for_function('window.modelStudio.selection.auto===false')
            assert app._model_selection.state['auto'] is False
            await page.locator('#expression-list').get_by_role('button',name='Happy',exact=True).click()
            await page.wait_for_function("window.modelStudio.selection.expression==='__chassie__/happy.exp3.json'")
            await page.locator('.interaction-settings summary').click()
            await page.locator('#interaction-gaze_radius').fill('320')
            await page.locator('#interaction-gaze_radius').dispatch_event('change')
            await page.wait_for_function('window.modelStudio.selection.interaction.gaze_radius===320')
            assert app._model_selection.state['interaction']['gaze_radius']==320
            await page.locator('#interaction-headpat_enabled').uncheck()
            await page.wait_for_function('window.modelStudio.selection.interaction.headpat_enabled===false')
            await page.screenshot(path=str(artifacts/'Model_4-interaction-settings.png'))
            await page.locator('#reset-interaction').click()
            await page.wait_for_function('window.modelStudio.selection.interaction.gaze_radius===180 && window.modelStudio.selection.interaction.headpat_enabled')
            assert await page.locator('.studio-shell').evaluate('(el)=>el.inert')
            await page.locator('#close-models').click()
            await app._broadcast_to_ui({'type':'subtitle','generation':10,'text':'This is a subtitle preview.'})
            await page.get_by_text('This is a subtitle preview.',exact=True).wait_for()
            assert await page.locator('#open-models').evaluate('(el)=>el===document.activeElement')
            await page.locator('#toggle-chat').click()
            a=await page.locator('#open-models').bounding_box();b=await page.locator('#reopen-chat').bounding_box()
            assert a['y']+a['height']<=b['y'] or b['y']+b['height']<=a['y'] or a['x']+a['width']<=b['x'] or b['x']+b['width']<=a['x']
            await page.screenshot(path=str(artifacts/'collapsed-chat.png'))
            await page.locator('#reopen-chat').click()
            await page.screenshot(path=str(artifacts/'subtitle.png'))
            await page.set_viewport_size({'width':390,'height':844})
            await page.locator('#toggle-chat').click()
            await page.screenshot(path=str(artifacts/'mobile.png'))
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.goto(url+'/?panel=models')
            await page.locator('#auto-expression').wait_for()
            assert not await page.locator('#avatar-canvas').is_visible()
            await page.keyboard.press('Escape')
            assert await page.locator('#auto-expression').is_visible()
            await page.screenshot(path=str(artifacts/'embedded-escape.png'))
            await page.goto(url+'/?panel=chat')
            await page.wait_for_function("!document.getElementById('mic-toggle').disabled")
            items=[{'role':'user' if i%2 else 'assistant','text':f'Synthetic scrolling message {i}. '+('Long enough to wrap. '*4)} for i in range(30)]
            await app._broadcast_to_ui({'type':'history_snapshot','items':items})
            await page.wait_for_function("document.querySelectorAll('.message-bubble').length===30")
            messages=page.locator('#messages-container')
            assert await messages.evaluate('(el)=>getComputedStyle(el).scrollbarWidth')=='none'
            assert await messages.evaluate('(el)=>el.scrollHeight>el.clientHeight')
            await messages.evaluate('(el)=>el.scrollTop=0')
            await messages.hover()
            await page.mouse.wheel(0,400)
            await page.wait_for_function("document.getElementById('messages-container').scrollTop>0")
            await page.screenshot(path=str(artifacts/'chat-no-scrollbar.png'))
            assert not errors,errors
            await browser.close()
    finally:await runner.cleanup()
