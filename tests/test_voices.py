import pytest
import yaml
from unittest.mock import AsyncMock, Mock
from speech import voices
from test_orchestrator import app  # noqa: F401

TABLE = '''| VVM | キャラクター | スタイル | ID |
| --- | --- | --- | --- |
| 3.vvm | 波音リツ | ノーマル | 9 |
| 3.vvm | 波音リツ | クイーン | 65 |
| 15.vvm | もち子さん | ノーマル | 20 |
'''


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'models/vvms').mkdir(parents=True)
    (tmp_path / 'models/README.txt').write_text('intro\n' + TABLE, encoding='utf-8')
    (tmp_path / 'models/TERMS.txt').write_text('Terms text', encoding='utf-8')
    (tmp_path / 'models/vvms/15.vvm').write_bytes(b'x')
    fake = tmp_path / 'download'  # Stands in for the official tool: writes <output>/models/vvms/<pattern>.
    fake.write_text('#!/bin/sh\nread answer\n[ "$answer" = y ] || exit 3\nmkdir -p "$8/models/vvms" && echo voice > "$8/models/vvms/$4"\n')
    fake.chmod(0o755)
    return tmp_path


def test_catalog_lists_every_voice_with_install_state(root):
    assert voices.catalog(root) == [
        {'pack': '3.vvm', 'character': '波音リツ', 'style': 'ノーマル', 'id': 9, 'installed': False},
        {'pack': '3.vvm', 'character': '波音リツ', 'style': 'クイーン', 'id': 65, 'installed': False},
        {'pack': '15.vvm', 'character': 'もち子さん', 'style': 'ノーマル', 'id': 20, 'installed': True}]
    assert voices.credit('もち子さん') == 'VOICEVOX:もち子(cv 明日葉よもぎ)' and voices.credit('波音リツ') == 'VOICEVOX:波音リツ'
    assert voices.voice(root, 65)['character'] == '波音リツ' and voices.voice(root, 999) is None


def test_download_adds_only_that_pack(root):
    voices.download(root, '3.vvm')
    assert (root / 'models/vvms/3.vvm').read_text() == 'voice\n' and (root / 'models/vvms/15.vvm').read_bytes() == b'x'
    assert [p.name for p in root.iterdir() if p.name.startswith('tmp')] == []
    with pytest.raises(ValueError): voices.download(root, '../x.vvm')


@pytest.mark.asyncio
async def test_set_voice_saves_style_and_previews(app, root, tmp_path):
    app._voicevox_root, app._local_config_root = root, tmp_path
    app._tts = Mock(set_style=AsyncMock())
    app._preview_voice = AsyncMock()
    with pytest.raises(ValueError, match='Download'): await app.handle_control({'type': 'set_voice', 'style': 65})
    with pytest.raises(ValueError, match='terms'): await app.handle_control({'type': 'download_voice', 'pack': '3.vvm'})
    app._voice_sizes = {'3.vvm': 58_000_000}
    result = await app.handle_control({'type': 'download_voice', 'pack': '3.vvm', 'accept_terms': True})
    assert result['type'] == 'voices' and result['sizes'] == {'3.vvm': 58_000_000} and result['terms'] == 'Terms text'
    await app.handle_control({'type': 'set_voice', 'style': 65})
    app._tts.set_style.assert_awaited_once_with(65); app._preview_voice.assert_awaited_once()
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text()) == {'tts': {'style': 65}}
    assert app._settings()['voice'] == {'style': 65, 'character': '波音リツ', 'style_name': 'クイーン', 'credit': 'VOICEVOX:波音リツ'}


@pytest.mark.asyncio
async def test_voice_panel_download_and_choose(app, root, tmp_path):
    from aiohttp import web
    from playwright.async_api import async_playwright
    app._voicevox_root, app._local_config_root, app._voice_sizes = root, tmp_path, {'3.vvm': 58_000_000}
    app._tts = Mock(set_style=AsyncMock(), status=Mock(return_value=None)); app._preview_voice = AsyncMock()
    runner = web.AppRunner(app._web_app); await runner.setup(); site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 440, 'height': 900}); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.goto(url + '/?panel=settings')
            await page.get_by_text('Her voice', exact=True).click()
            await page.locator('#load-voices').click()
            await page.get_by_text('More voices to download (1 packs)', exact=True).click()
            await page.get_by_text('Pack 3 · 1 character · 58 MB: 波音リツ', exact=True).wait_for()
            await page.get_by_role('button', name='Download').click()
            await page.get_by_text('Accept the VOICEVOX terms below first.', exact=True).wait_for()
            await page.locator('#voice-terms-accept').check()
            await page.get_by_role('button', name='Download').click()
            await page.get_by_role('button', name='クイーン').click()
            await page.wait_for_function("document.getElementById('speech-credit').textContent==='VOICEVOX:波音リツ'")
            await page.get_by_role('button', name='クイーン ✓').wait_for()
            assert (root / 'models/vvms/3.vvm').is_file() and not errors
            await browser.close()
    finally:
        await runner.cleanup()
