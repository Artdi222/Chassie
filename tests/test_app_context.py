import asyncio
import json
import subprocess
from unittest.mock import Mock

import pytest

from vision.app_context import active_application
from test_orchestrator import app, playback_fixture


def test_hyprland_reads_only_app_class_without_capture(monkeypatch):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE', 'test')
    monkeypatch.setattr('vision.app_context.shutil.which', lambda _: '/usr/bin/hyprctl')
    run = Mock(return_value=json.dumps({'class': 'code', 'title': 'private document',
                                       'pid': 123, 'address': 'secret'}).encode())
    monkeypatch.setattr('vision.app_context.subprocess.check_output', run)
    assert active_application() == {'available': True, 'app': 'code'}
    assert run.call_args.args[0] == ['hyprctl', '-j', 'activewindow']
    assert run.call_args.kwargs['timeout'] <= .25


@pytest.mark.parametrize('result', [b'{}', b'[]', b'null', b'not json', b'{"class": null}',
                                     subprocess.TimeoutExpired('hyprctl', .25), OSError('unavailable')])
def test_missing_or_failed_app_lookup_is_unknown(monkeypatch, result):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE', 'test')
    monkeypatch.setattr('vision.app_context.shutil.which', lambda _: '/usr/bin/hyprctl')
    run = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr('vision.app_context.subprocess.check_output', run)
    assert active_application() == {'available': False}


def test_unsupported_desktop_does_not_capture(monkeypatch):
    monkeypatch.delenv('HYPRLAND_INSTANCE_SIGNATURE', raising=False)
    run = Mock()
    monkeypatch.setattr('vision.app_context.subprocess.check_output', run)
    assert active_application() == {'available': False}
    run.assert_not_called()


def test_overlay_uses_live_external_focus_order_without_window_contents(monkeypatch):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE','test')
    monkeypatch.setattr('vision.app_context.shutil.which',lambda _:'/usr/bin/hyprctl')
    overlay={'class':'chassie-overlay','title':'Chassie — Conversation'}
    clients=[{'class':'firefox','focusHistoryID':4,'mapped':True},
             {'class':'chassie-overlay','focusHistoryID':0,'mapped':True},
             {'class':'renamed-overlay','initialClass':'chassie-overlay','focusHistoryID':1,'mapped':True},
             {'class':'code','focusHistoryID':2,'mapped':True,'title':'private document'},
             {'class':'closed-app','focusHistoryID':1,'mapped':False},
             {'class':'hidden-app','focusHistoryID':1,'mapped':True,'hidden':True},
             {'class':'never-focused','focusHistoryID':-1,'mapped':True},
             {'class':'bad-rank','focusHistoryID':'0','mapped':True}]
    run=Mock(side_effect=[json.dumps(overlay),json.dumps(clients)])
    monkeypatch.setattr('vision.app_context.subprocess.check_output',run)
    assert active_application()=={'available':True,'app':'code',
        'source':'last_external_focus','overlay_focused':True}
    assert [c.args[0][-1] for c in run.call_args_list]==['activewindow','clients']
    assert all(0<c.kwargs['timeout']<=.25 for c in run.call_args_list)


@pytest.mark.parametrize('clients',[[],[{'class':'chassie-overlay','focusHistoryID':0,'mapped':True}],
                                  {},None,'bad json'])
def test_overlay_without_valid_external_focus_is_unknown(monkeypatch,clients):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE','test')
    monkeypatch.setattr('vision.app_context.shutil.which',lambda _:'/usr/bin/hyprctl')
    run=Mock(side_effect=['{"class":"chassie-overlay"}',json.dumps(clients)])
    monkeypatch.setattr('vision.app_context.subprocess.check_output',run)
    assert active_application()['available'] is False


def test_overlay_lookup_refreshes_and_obeys_total_time_budget(monkeypatch):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE','test')
    monkeypatch.setattr('vision.app_context.shutil.which',lambda _:'/usr/bin/hyprctl')
    run=Mock(side_effect=['{"class":"chassie-overlay"}',
                         '[{"class":"code","mapped":true,"focusHistoryID":1}]',
                         '{"class":"chassie-overlay"}','[]',
                         '{"class":"chassie-overlay"}'])
    monkeypatch.setattr('vision.app_context.subprocess.check_output',run)
    monkeypatch.setattr('vision.app_context.time.monotonic',Mock(side_effect=[0,.1,1,1.1,2,2.3]))
    assert active_application()['app']=='code'
    assert active_application()['available'] is False
    assert active_application()['available'] is False
    assert run.call_count==5  # No clients query once the time budget expired.


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['text', 'voice'])
async def test_app_metadata_without_vision_refreshes_and_clears_each_turn(app, monkeypatch, source):
    playback = playback_fixture(app); playback.first_release.set()
    app._config['app_context'] = {'enabled': True}
    lookup = Mock(side_effect=[{'available': True, 'app': 'code'}, {'available': False}])
    monkeypatch.setattr('brain.orchestrator.active_application', lookup)
    seen = []
    async def stream(text, **kwargs):
        seen.append(kwargs)
        yield '[neutral] Hello.'
    app._hermes.stream_message = stream
    for message in ('App apa yang aku buka?', 'Sekarang?'):
        await app._run_turn({'text': message, 'source': source})
        assert app._turn_app is None
    assert json.loads(seen[0]['context'])['active_application']['app'] == 'code'
    assert json.loads(seen[1]['context'])['active_application']['available'] is False
    for request in seen:
        assert 'images' not in request
        assert 'vision' not in json.loads(request['context'])


@pytest.mark.asyncio
async def test_disabled_app_metadata_never_queries_desktop(app, monkeypatch):
    playback = playback_fixture(app); playback.first_release.set()
    lookup = Mock()
    monkeypatch.setattr('brain.orchestrator.active_application', lookup)
    await app._run_turn({'text': 'Hello', 'source': 'text'})
    lookup.assert_not_called()


@pytest.mark.asyncio
async def test_overlay_app_context_labels_previous_focus_without_images(app,monkeypatch):
    playback=playback_fixture(app);playback.first_release.set()
    app._config['app_context']={'enabled':True}
    monkeypatch.setattr('brain.orchestrator.active_application',lambda:{'available':True,'app':'code',
        'source':'last_external_focus','overlay_focused':True})
    seen=[]
    async def stream(text,**kwargs):
        seen.append(kwargs);yield '[neutral] Hello.'
    app._hermes.stream_message=stream
    await app._run_turn({'text':'Lagi buka apa?','source':'text'})
    context=json.loads(seen[0]['context'])['active_application']
    assert context['app']=='code' and context['source']=='last_external_focus'
    assert 'before opening Chassie chat' in context['note']
    assert 'images' not in seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_failed_or_cancelled_turn_releases_app_metadata(app, monkeypatch, cancel):
    playback = playback_fixture(app); playback.first_release.set()
    app._config['app_context'] = {'enabled': True}
    monkeypatch.setattr('brain.orchestrator.active_application', lambda: {'available': True, 'app': 'code'})
    async def stream(text, **kwargs):
        assert json.loads(kwargs['context'])['active_application']['app'] == 'code'
        if cancel:
            raise asyncio.CancelledError()
        raise RuntimeError('Synthetic provider error')
        yield
    app._hermes.stream_message = stream
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await app._run_turn({'text': 'Hello', 'source': 'text'})
    else:
        await app._run_turn({'text': 'Hello', 'source': 'text'})
    assert app._turn_app is None
