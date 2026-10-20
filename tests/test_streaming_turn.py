import asyncio

import pytest
from aiohttp import web
from hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG

from test_orchestrator import app, playback_fixture


@pytest.mark.asyncio
async def test_stop_during_sentence_pause_discards_prefetched_audio(app, monkeypatch):
    from speech_pacing import SpeechPacing
    playback = playback_fixture(app); playback.first_release.set()
    between = asyncio.Event()
    original = SpeechPacing.delay
    def delay(pacing, chunks, *, now):
        value = original(pacing, chunks, now=now)
        if value:
            between.set()
            return 30
        return value
    monkeypatch.setattr(SpeechPacing, 'delay', delay)
    app._turn_task = asyncio.create_task(app._run_turn({'text': 'explain', 'source': 'text'}))
    try:
        await asyncio.wait_for(between.wait(), 2)
        assert app._spoken.strip() == 'First sentence.'
        await asyncio.wait_for(app.handle_control({'type': 'stop'}), 1)
        assert playback.enqueued == [1]
        assert app._spoken.strip() == 'First sentence.'
        assert app._stream_view['interrupted']
    finally:
        if app._turn_task:
            app._turn_task.cancel()
            await asyncio.gather(app._turn_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_timeout_before_text_is_visible_in_chat_and_returns_to_idle(app):
    playback_fixture(app)
    async def stream(*args,**kwargs):
        raise RuntimeError('Hermes streaming request timed out. Please retry.')
        yield
    app._hermes.stream_message=stream
    await asyncio.wait_for(app._run_turn({'text':'hello','source':'text'}),2)
    events=[call.args[0] for call in app._broadcast_to_ui.call_args_list]
    errors=[event for event in events if event.get('type')=='notice' and event.get('scope')=='chat']
    assert len(errors)==1 and 'timed out' in errors[0]['text']
    assert errors[0]['stream_id']==app._stream_view['id']
    assert errors[0]['retry_text']=='hello'
    assert app._current_status in ('idle','listening')
    app._hermes.complete_response.assert_not_called()
    assert app._stream_view['done'] and app._stream_view['interrupted']


@pytest.mark.asyncio
async def test_first_playback_starts_before_hermes_completes(app):
    playback=playback_fixture(app)
    release=asyncio.Event();closed=asyncio.Event()
    async def stream(*args,**kwargs):
        try:
            yield '[hap'
            yield 'py] First sentence. '
            await release.wait()
            yield 'Second sentence.'
        finally: closed.set()
    app._hermes.stream_message=stream
    task=asyncio.create_task(app._run_turn({'text':'explain','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        assert not release.is_set() and not closed.is_set()
        app._hermes.send_message.assert_not_called()
        assert playback.starts==['First sentence.']
        assert app._spoken==''
        release.set();playback.first_release.set()
        await asyncio.wait_for(task,2)
        assert app._spoken.strip()=='First sentence. Second sentence.'
        assert closed.is_set()
    finally:
        release.set();playback.first_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_guest_cancels_open_stream_and_current_playback(app):
    playback=playback_fixture(app)
    release=asyncio.Event();closed=asyncio.Event()
    async def stream(*args,**kwargs):
        try:
            yield '[happy] First sentence. '
            await release.wait()
            yield 'Private late sentence.'
        finally: closed.set()
    app._hermes.stream_message=stream
    app._turn_task=asyncio.create_task(app._run_turn({'text':'private request','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        before_cancel=len(app._broadcast_to_ui.call_args_list)
        await asyncio.wait_for(app.handle_control({'type':'guest_present','name':'Guest'}),2)
        assert closed.is_set()
        assert app._spoken=='' and playback.starts==['First sentence.']
        app._hermes.clear_history.assert_called()
        assert app._stream_view is None
        assert not any(call.args[0].get('type')=='chat_stream'
                       for call in app._broadcast_to_ui.call_args_list[before_cancel:])
    finally:
        release.set();playback.first_release.set()


@pytest.mark.asyncio
async def test_stream_failure_stops_playback_and_prefetch(app):
    playback=playback_fixture(app,block_second_synthesis=True)
    async def stream(*args,**kwargs):
        yield '[happy] First sentence. Second sentence. '
        await playback.second_started.wait()
        raise RuntimeError('Synthetic stream failed')
    app._hermes.stream_message=stream
    task=asyncio.create_task(app._run_turn({'text':'explain','source':'text'}))
    try:
        await asyncio.wait_for(task,2)
        assert playback.second_cancelled.is_set()
        assert app._spoken==''
        app._hermes.complete_response.assert_not_called()
        app._audio_player.cancel_utterance.assert_called()
        assert app._stream_view['interrupted']
    finally:
        playback.first_release.set();playback.second_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_real_sse_to_tts_before_network_done_and_history_after_drain(app):
    import json
    playback=playback_fixture(app)
    release=asyncio.Event();sent_finish=asyncio.Event()
    async def endpoint(request):
        body=await request.json()
        assert body['stream'] is True
        response=web.StreamResponse(headers={'Content-Type':'text/event-stream'})
        await response.prepare(request)
        async def delta(text):
            data={'choices':[{'index':0,'delta':{'content':text},'finish_reason':None}]}
            await response.write(('data: '+json.dumps(data)+'\n\n').encode())
        await delta('[happy] First sentence. ')
        await release.wait()
        await delta('Second sentence.')
        await response.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        sent_finish.set()
        return response
    server=web.Application();server.router.add_post('/v1/chat/completions',endpoint)
    runner=web.AppRunner(server);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    config={**CONFIG,'hermes':{**CONFIG['hermes'],'gateway_url':f'http://127.0.0.1:{port}'}}
    bridge=HermesBridge(config);await bridge.connect();app._hermes=bridge
    task=asyncio.create_task(app._run_turn({'text':'synthetic integration','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        assert not sent_finish.is_set()
        assert app._turn_metrics['first_audio_queued_seconds']>=0
        assert 'hermes_complete_seconds' not in app._turn_metrics
        assert app._spoken==''
        snapshot=app._history_snapshot()
        assert snapshot['items']==[{'role':'user','text':'synthetic integration'},
            {'role':'assistant','text':'[happy] First sentence.','stream_id':app._stream_view['id']}]
        assert any(c.args[0].get('type')=='chat_stream' and c.args[0]['text']=='[happy] First sentence.'
                   for c in app._broadcast_to_ui.call_args_list)
        release.set();playback.first_release.set()
        await asyncio.wait_for(task,2)
        assert bridge._pending is None
        assert app._spoken.strip()=='First sentence. Second sentence.'
        assert app._stream_view['text']=='[happy] First sentence. [happy] Second sentence.'
        assert 'stream_id' not in app._history_snapshot()['items'][-1]
    finally:
        release.set();playback.first_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await bridge.close();await runner.cleanup()


@pytest.mark.asyncio
async def test_slow_playback_backpressures_text_stream(app):
    playback=playback_fixture(app)
    chunks=[];closed=asyncio.Event()
    async def stream(*a,**kw):
        try:
            for index in range(1000):
                chunks.append(index)
                yield f'[happy] Sentence {index} ends. '
        finally: closed.set()
    app._hermes.stream_message=stream
    task=asyncio.create_task(app._run_turn({'text':'long answer','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        await asyncio.sleep(.02)
        # Current + prefetched + queue8 + one producer waiting to enqueue.
        assert len(chunks)<=11
    finally:
        task.cancel();playback.first_release.set()
        await asyncio.gather(task,return_exceptions=True)
    assert closed.is_set()
