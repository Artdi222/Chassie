import json
from pathlib import Path

import pytest
from aiohttp import ClientSession, web

from avatar.catalog import ModelCatalog, ModelSelection, active_files
from desktop.model import prepare_entry
from test_orchestrator import app


def test_available_models_exclude_removed_model_and_model_four_assets_are_valid(tmp_path):
    catalog=ModelCatalog()
    assert not catalog.errors
    assert set(catalog.models)=={'Model_4'}
    assert catalog.get('Model_4').public()['name']=='Tian Muzi'
    assert len(catalog.get('Model_4').expressions)==8
    with pytest.raises(ValueError):catalog.get('Model_3')
    for entry in [catalog.get('Model_4')]:
        original=entry.path.read_bytes()
        native=prepare_entry(entry,tmp_path)
        refs=json.loads(native.read_text())['FileReferences']
        assert (native.parent/refs['Moc']).is_file()
        assert all((native.parent/p).is_file() for p in refs['Textures'])
        for expression in refs['Expressions']:
            params=json.loads((native.parent/expression['File']).read_text())['Parameters']
            assert params and all(p['Id'] in entry.parameter_ids for p in params)
            assert not any(p['Id']=='ParamMouthOpenY' for p in params)
        assert entry.path.read_bytes()==original
        assert all('costume_v0100' not in x['id'] for x in entry.expressions)


def test_selection_validation_is_atomic_and_switch_clears_model_specific_options(tmp_path):
    c=ModelCatalog();selection=ModelSelection(c,tmp_path/'selection.json')
    selection.change({'model_id':'Model_4','auto':False,'expression':'__chassie__/sad.exp3.json'})
    before=selection.payload()
    with pytest.raises(ValueError):selection.change({'model_id':'Model_4','outfit':'animation/smile.exp3.json'})
    with pytest.raises(ValueError):selection.change({'model_id':'Model_1'})
    assert selection.payload()==before
    assert active_files(c.get('Model_4'),selection.state,'happy')==['__chassie__/sad.exp3.json']
    selection.change({'model_id':'Model_4','auto':True})
    assert '__chassie__/happy.exp3.json' in active_files(c.get('Model_4'),selection.state,'happy')
    assert selection.state['outfit'] is None
    assert ModelSelection(c,tmp_path/'selection.json').state['model_id']=='Model_4'


@pytest.mark.asyncio
async def test_model_routes_only_serve_catalogued_renderer_assets(app):
    runner=web.AppRunner(app._web_app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    try:
        async with ClientSession() as client:
            async with client.get(url+'/api/models') as response:
                assert {m['id'] for m in (await response.json())['models']}=={'Model_4'}
            async with client.get(url+'/api/models/Model_3/model.json') as response:
                assert response.status==404
            async with client.get(url+'/api/models/Model_4/model.json') as response:
                manifest=await response.json()
            async with client.get(url+manifest['FileReferences']['Moc']) as response:assert response.status==200
            for path in ['../../config.yaml','../tuzi_mian__2_.zip','../../../config.yaml']:
                async with client.get(url+'/api/models/Model_4/assets/'+path) as response:assert response.status==404
            with pytest.raises(ValueError):await app.handle_control({'type':'select_model','model_id':'Model_1'})
            assert app._model_selection.state['model_id']=='Model_4'
    finally:await runner.cleanup()


def test_interaction_preferences_persist_per_model_and_validate_atomically(tmp_path):
    catalog=ModelCatalog();path=tmp_path/'selection.json'
    selection=ModelSelection(catalog,path)
    selection.change({'model_id':'Model_4','interaction':{'gaze_radius':320,'headpat_delay':.4,'follow_speed':1.5}})
    selection=ModelSelection(catalog,path)
    assert selection.state['interaction']['gaze_radius']==320
    assert selection.state['interaction']['headpat_delay']==.4
    before=path.read_bytes()
    for invalid in ({'gaze_radius':401},{'follow_speed':float('nan')},{'headpat_enabled':'true'}):
        with pytest.raises(ValueError):selection.change({'model_id':'Model_4','interaction':invalid})
        assert path.read_bytes()==before
