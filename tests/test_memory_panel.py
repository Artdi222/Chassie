import pytest
from aiohttp import web
from playwright.async_api import async_playwright
from test_orchestrator import app  # noqa: F401
from unittest.mock import Mock
from memory.vault import VaultMemory


def test_vault_list_carries_category_date_importance_and_superseded():
    vault = VaultMemory.__new__(VaultMemory)
    vault.store = Mock()
    vault.store.list.return_value = [
        {'id': 'c1', 'path': '_generated/chassie/Plans/a.md', 'content': '# Trip\n\nGo to Bali in May.'},
        {'id': 'c2', 'path': 'Daily/2026-11-01.md', 'content': 'A note of mine.'}]
    vault.store.facts.return_value = [{'path': '_generated/chassie/Plans/a.md', 'date': '2026-11-20', 'importance': 3,
                                       'superseded_by': 'f' * 24}]
    a, b = vault.list()
    assert a == {'id': 'c1', 'content': 'Go to Bali in May.', 'source': '_generated/chassie/Plans/a.md', 'editable': True,
                 'category': 'Plans', 'date': '2026-11-20', 'importance': 3, 'superseded': True}
    assert b['category'] == 'Notes' and b['editable'] is False and b['superseded'] is False and b['date'] == ''


@pytest.mark.asyncio
async def test_two_hundred_memories_render_collapsed_and_filter(app):
    app._automatic_memory = True
    owner = app._memory.create_profile('Synthetic owner', consent=True); app._session_context.set_owner(owner.id)
    categories = ['People', 'Events', 'Plans', 'Technical']
    items = [{'id': f'm{i}', 'content': f'Fact number {i}' + (' about tea' if i == 137 else ''), 'source': 'x.md', 'editable': True,
              'category': categories[i % 4], 'date': f'2026-11-{i % 28 + 1:02d}', 'importance': 2, 'superseded': i == 3} for i in range(200)]
    app._vault = Mock(status=Mock(return_value={'available': True, 'path': '/synthetic', 'chunks': 200}), list=Mock(return_value=items))
    runner = web.AppRunner(app._web_app); await runner.setup(); site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 440, 'height': 900}); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.goto(url + '/?panel=settings')
            await page.get_by_role('tab', name='People & memory').click()
            await page.get_by_text('Saved memories', exact=True).click()
            await page.wait_for_function("!document.getElementById('load-memories').disabled")
            await page.locator('#load-memories').click()
            await page.get_by_text('Technical (49)', exact=True).wait_for()  # Item 3 (Technical) is replaced: hidden.
            assert await page.locator('.memory-group[open]').count() == 0
            assert await page.locator('.memory-group').count() == 4
            await page.get_by_text('People (50)', exact=True).click()
            assert await page.locator('.memory-group[open] .memory-item').count() == 20
            await page.get_by_role('button', name='Show more (30 left)').click()
            assert await page.locator('.memory-group[open] .memory-item').count() == 40
            await page.locator('#memory-search').fill('tea')
            await page.get_by_text('Fact number 137 about tea', exact=True).wait_for()
            assert await page.locator('.memory-item').count() == 1
            await page.locator('#memory-search').fill('')
            await page.locator('#memory-replaced').check()
            await page.get_by_text('Technical (50)', exact=True).wait_for()
            assert await page.evaluate("getComputedStyle(document.getElementById('memory-list')).overflowY") == 'auto'
            assert not errors
            await browser.close()
    finally:
        await runner.cleanup()
