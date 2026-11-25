"""First-run setup: installing a downloaded Live2D model and finishing onboarding."""
import io
import json
import zipfile

import pytest
from aiohttp import ClientSession, FormData, web

from avatar.catalog import ModelCatalog, ModelSelection
from avatar.importer import ImportError_, install
from test_orchestrator import app  # noqa: F401  (fixture)

MODEL3 = {'Version': 3, 'FileReferences': {'Moc': 'Hiyori.moc3', 'Textures': ['tex/texture_00.png']}}


def package_zip(prefix='Download/Hiyori Free/runtime/', extras=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr(prefix + 'Hiyori.model3.json', json.dumps(MODEL3))
        z.writestr(prefix + 'Hiyori.moc3', b'MOC3fake')
        z.writestr(prefix + 'tex/texture_00.png', b'png')
        z.writestr('Download/Hiyori Free/artwork.psd', b'x' * 1000)
        z.writestr('__MACOSX/Download/._Hiyori.model3.json', b'junk')
        for name, data in extras:
            z.writestr(name, data)
    return buffer.getvalue()


def test_installs_only_the_model_package_from_a_messy_download(tmp_path):
    archive = tmp_path / 'download.zip'
    archive.write_bytes(package_zip(extras=[('../escape.txt', b'no'), ('/abs.txt', b'no')]))
    installed = install(archive, tmp_path / 'model')
    # A generic 'runtime' folder takes the download's name instead.
    assert installed == ['download']
    root = tmp_path / 'model' / 'download'
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()) == [
        'Hiyori.moc3', 'Hiyori.model3.json', 'tex/texture_00.png']
    assert not (tmp_path / 'escape.txt').exists() and not list((tmp_path / 'model').glob('.import-*'))
    assert list(ModelCatalog(tmp_path / 'model').models) == ['download']
    # Installing again never overwrites the first copy.
    assert install(archive, tmp_path / 'model') == ['download 2']


def test_explains_archives_that_are_not_usable_models(tmp_path):
    old = tmp_path / 'old.zip'
    with zipfile.ZipFile(old, 'w') as z:
        z.writestr('Shizuku/shizuku.model.json', '{}')
        z.writestr('Shizuku/shizuku.moc', b'')
    with pytest.raises(ImportError_, match='Cubism 2'):
        install(old, tmp_path / 'model')
    empty = tmp_path / 'art.zip'
    with zipfile.ZipFile(empty, 'w') as z:
        z.writestr('art.psd', b'')
    with pytest.raises(ImportError_, match='No Live2D model found'):
        install(empty, tmp_path / 'model')
    (tmp_path / 'fake.zip').write_bytes(b'nope')
    with pytest.raises(ImportError_, match='not a zip'):
        install(tmp_path / 'fake.zip', tmp_path / 'model')


@pytest.mark.asyncio
async def test_onboarding_imports_a_model_and_completes(app, tmp_path):
    catalog = ModelCatalog(tmp_path / 'model')
    app._catalog = catalog
    app._model_selection = ModelSelection(catalog, tmp_path / 'data' / 'model-selection.json')
    runner = web.AppRunner(app._web_app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    try:
        async with ClientSession() as http:
            async with http.get(base + '/', allow_redirects=False) as r:
                assert r.status == 302 and r.headers['Location'] == '/onboarding'
            async with http.get(base + '/api/onboarding') as r:
                assert await r.json() == {'completed': False, 'has_model': False, 'model_id': None}
            async with http.post(base + '/api/onboarding') as r:
                assert r.status == 409  # Cannot finish without a model.
            async with http.post(base + '/api/models/import', headers={'Origin': 'http://evil.example'},
                                 data={'files': b''}) as r:
                assert r.status == 403
            form = FormData(); form.add_field('files', b'not a zip', filename='bad.zip')
            async with http.post(base + '/api/models/import', data=form) as r:
                assert r.status == 400 and 'not a zip' in (await r.json())['error']
            # A folder upload: each file carries its path inside the picked folder.
            form = FormData()
            form.add_field('files', json.dumps(MODEL3).encode(), filename='Hiyori/Hiyori.model3.json')
            form.add_field('files', b'MOC3fake', filename='Hiyori/Hiyori.moc3')
            form.add_field('files', b'png', filename='Hiyori/tex/texture_00.png')
            async with http.post(base + '/api/models/import', data=form) as r:
                body = await r.json()
                assert r.status == 200, body
            assert body['installed'] == ['Hiyori'] and body['selected'] == 'Hiyori'
            assert app._model_selection.state['model_id'] == 'Hiyori'
            form = FormData(); form.add_field('files', package_zip(), filename='Hiyori Free.zip')
            async with http.post(base + '/api/models/import', data=form) as r:
                assert (await r.json())['installed'] == ['Hiyori Free']
            assert app._model_selection.state['model_id'] == 'Hiyori'  # Keeps the current choice.
            async with http.post(base + '/api/onboarding') as r:
                assert (await r.json())['completed'] is True
            async with http.get(base + '/', allow_redirects=False) as r:
                assert r.status == 200
            async with http.get(base + '/onboarding') as r:
                assert 'Choose .zip file' in await (await http.get(base + '/importer.js')).text()
                assert 'Welcome to Chassie' in await r.text()
    finally:
        await runner.cleanup()
