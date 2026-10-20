import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock

import pytest
from orchestrator import Orchestrator
from stt_engine import SpeechEvent

@pytest.fixture
def app(tmp_path):
    stt=Mock(epoch=0,muted=False,error=None)
    def mute(value):
        stt.muted=value;stt.epoch+=1
    stt.set_muted.side_effect=mute
    stt.invalidate.side_effect=lambda:setattr(stt,'epoch',stt.epoch+1)
    stt.is_listening.return_value=False
    hermes=Mock(send_message=AsyncMock(return_value='[happy] Hello.'),get_history=Mock(return_value=[]),close=AsyncMock())
    async def stream(*args,**kwargs):
        yield await hermes.send_message(*args,**kwargs)
    hermes.stream_message=stream
    vts=Mock(trigger_emotion=AsyncMock(return_value=True),set_mouth_open=AsyncMock(),reset_expressions=AsyncMock(),disconnect=AsyncMock(),is_authenticated=False)
    vts.get_capabilities.return_value={'emotions':{}}
    player=Mock(cancel_utterance=Mock(),flush_effects=AsyncMock())
    face=Mock(get_context_string=Mock(return_value=''),get_observation=Mock(return_value={'available':False,'face_count':0,'expression':'unknown','observed_at':0,'identity_verified':False}))
    config={'audio':{'sample_rate':16000,'output_sample_rate':24000},'stt':{},'tts':{},'hermes':{},
            'companion':{'memory_path':str(tmp_path/'memory.sqlite')},'conversation':{'input_mode':'review'}}
    result=Orchestrator(config,components={'stt':stt,'hermes':hermes,'vts':vts,'player':player,'face':face,'tts':Mock(),'analyzer':Mock()})
    yield result
    result._memory.close()

@pytest.mark.asyncio
async def test_mode_does_not_depend_on_browser_count(app):
    app._broadcast_to_ui=AsyncMock()
    await app._handle_speech_event(SpeechEvent('transcript',0,0,1,'hello'))
    assert app._ui_input_queue.empty()
    app._input_mode='hands_free'
    await app._handle_speech_event(SpeechEvent('transcript',0,0,1,'hello'))
    assert (await app._ui_input_queue.get())['text']=='hello'

@pytest.mark.asyncio
async def test_mute_purges_pending_voice_but_preserves_typed_input(app):
    app._broadcast_to_ui=AsyncMock()
    await app._ui_input_queue.put({'text':'old','source':'voice'})
    await app._ui_input_queue.put({'text':'typed','source':'text'})
    await app.handle_control({'type':'set_mic','enabled':False})
    assert app._stt.muted
    assert (await app._ui_input_queue.get())['text']=='typed'
    assert app._ui_input_queue.empty()

@pytest.mark.asyncio
async def test_guest_presence_cancels_personal_generation_and_clears_history(app):
    app._broadcast_to_ui=AsyncMock()
    p=app._memory.create_profile('Owner',consent=True)
    app._session_context.set_owner(p.id)
    app._memory.add_memory(p.id,'private detail',source='user',consent=True)
    assert 'private detail' in app._context_text()
    gate=asyncio.Event()
    app._turn_task=asyncio.create_task(gate.wait())
    await app.handle_control({'type':'guest_present','name':'Friend'})
    assert app._turn_task is None
    assert 'private detail' not in app._context_text()
    app._hermes.clear_history.assert_called()
    app._audio_player.cancel_utterance.assert_called()

@pytest.mark.asyncio
async def test_invalid_controls_do_not_change_microphone(app):
    with pytest.raises(ValueError): await app.handle_control({'type':'set_mic','enabled':'false'})
    app._stt.set_muted.assert_not_called()

@pytest.mark.asyncio
async def test_clear_cancels_inflight_and_invalidates_voice(app):
    app._broadcast_to_ui=AsyncMock()
    app._turn_task=asyncio.create_task(asyncio.sleep(10))
    await app.handle_control({'type':'clear_history'})
    assert app._turn_task is None
    app._stt.invalidate.assert_called()
    app._hermes.clear_history.assert_called()

@pytest.mark.asyncio
async def test_deselect_profile_removes_private_context_and_voice_draft(app):
    app._broadcast_to_ui=AsyncMock()
    p=app._memory.create_profile('Owner',consent=True)
    app._session_context.set_owner(p.id)
    app._memory.add_memory(p.id,'private secret',source='user',consent=True)
    await app.handle_control({'type':'select_profile','profile_id':None})
    assert 'private secret' not in app._context_text()
    app._broadcast_to_ui.assert_any_await({'type':'voice_draft_cleared'})

@pytest.mark.asyncio
async def test_absent_owner_cannot_list_or_mutate_personal_memories(app):
    app._broadcast_to_ui=AsyncMock()
    p=app._memory.create_profile('Owner',consent=True)
    app._session_context.set_owner(p.id)
    app._session_context.set_owner_present(False)
    with pytest.raises(ValueError): await app.handle_control({'type':'list_memories'})
    with pytest.raises(ValueError): await app.handle_control({'type':'add_memory','content':'x','consent':True})

@pytest.mark.asyncio
async def test_real_turn_cancel_during_hermes_never_reaches_tts(app):
    entered=asyncio.Event();release=asyncio.Event()
    async def delayed(*a,**kw):
        entered.set();await release.wait();return '[happy] Old answer'
    app._hermes.send_message=delayed
    app._broadcast_to_ui=AsyncMock()
    app._turn_task=asyncio.create_task(app._run_turn({'text':'personal request','source':'text'}))
    await entered.wait()
    await app.handle_control({'type':'guest_present','name':'Guest'})
    release.set()
    app._tts.synthesize_stream.assert_not_called()
    assert not any(c.args[0].get('role')=='assistant' for c in app._broadcast_to_ui.call_args_list)


def playback_fixture(app, *, block_second_synthesis=False):
    import threading
    import numpy as np
    starts=[];enqueued=[];begin_threads=[]
    first_draining=asyncio.Event();first_release=asyncio.Event()
    second_started=asyncio.Event();second_release=asyncio.Event()
    second_cancelled=asyncio.Event()
    app._broadcast_to_ui=AsyncMock()
    app._hermes.send_message=AsyncMock(return_value='[happy] First sentence. Second sentence. Third sentence.')
    async def synthesize(text):
        starts.append(text)
        if text=='Second sentence.':
            second_started.set()
            if block_second_synthesis:
                try: await second_release.wait()
                except asyncio.CancelledError:
                    second_cancelled.set();raise
        yield np.ones(480)
    app._tts.synthesize_stream=synthesize
    def begin(): begin_threads.append(threading.get_ident());return len(begin_threads)
    async def enqueue(pcm,**kwargs): enqueued.append(kwargs['generation']);return True
    async def drain(generation):
        if generation==1:
            first_draining.set();await first_release.wait()
    app._audio_player.begin_utterance=Mock(side_effect=begin)
    app._audio_player.enqueue=AsyncMock(side_effect=enqueue)
    app._audio_player.wait_until_done=AsyncMock(side_effect=drain)
    return SimpleNamespace(starts=starts,enqueued=enqueued,begin_threads=begin_threads,
        first_draining=first_draining,first_release=first_release,second_started=second_started,
        second_release=second_release,second_cancelled=second_cancelled)


@pytest.mark.asyncio
async def test_prefetch_is_one_sentence_ahead_and_spoken_requires_drain(app):
    import threading
    playback=playback_fixture(app)
    task=asyncio.create_task(app._run_turn({'text':'explain','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        await asyncio.wait_for(playback.second_started.wait(),.5)
        assert playback.starts==['First sentence.','Second sentence.']
        assert app._spoken==''
        assert playback.enqueued==[1]
        assert playback.begin_threads[0]!=threading.get_ident()
        playback.first_release.set()
        await asyncio.wait_for(task,2)
        assert playback.starts==['First sentence.','Second sentence.','Third sentence.']
        assert app._spoken.strip()=='First sentence. Second sentence. Third sentence.'
        app._hermes.complete_response.assert_called_once()
    finally:
        playback.first_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_during_playback_cancels_prefetch_without_heard_or_late_output(app):
    playback=playback_fixture(app,block_second_synthesis=True)
    task=asyncio.create_task(app._run_turn({'text':'private request','source':'text'}))
    app._turn_task=task
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        await asyncio.wait_for(playback.second_started.wait(),.5)
        await app.handle_control({'type':'guest_present','name':'Guest'})
        assert playback.second_cancelled.is_set()
        playback.first_release.set();playback.second_release.set()
        await asyncio.sleep(0)
        assert task.cancelled()
        assert playback.enqueued==[1]
        assert playback.starts==['First sentence.','Second sentence.']
        assert app._spoken==''
        app._hermes.complete_response.assert_not_called()
        app._hermes.clear_history.assert_called()
    finally:
        playback.first_release.set();playback.second_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_joins_delayed_begin_and_flushes_its_late_generation(app):
    import threading
    playback=playback_fixture(app)
    entered=threading.Event();release=threading.Event();cancelled_once=threading.Event()
    device={'active':False}
    def begin():
        entered.set();release.wait(2);device['active']=True;return 1
    def cancel(): device['active']=False;cancelled_once.set()
    app._audio_player.begin_utterance=Mock(side_effect=begin)
    app._audio_player.cancel_utterance=Mock(side_effect=cancel)
    app._turn_task=asyncio.create_task(app._run_turn({'text':'explain','source':'text'}))
    control=None
    try:
        for _ in range(100):
            if entered.is_set(): break
            await asyncio.sleep(.01)
        assert entered.is_set()
        control=asyncio.create_task(app.handle_control({'type':'stop'}))
        for _ in range(100):
            if cancelled_once.is_set(): break
            await asyncio.sleep(.01)
        assert cancelled_once.is_set()
        assert not control.done()
        release.set()
        await asyncio.wait_for(control,2)
        assert not device['active']
        assert not playback.enqueued
        assert app._spoken==''
    finally:
        release.set()
        if control: await asyncio.gather(control,return_exceptions=True)


@pytest.mark.asyncio
async def test_prefetch_failure_keeps_only_completed_current_sentence(app):
    playback=playback_fixture(app)
    original=app._tts.synthesize_stream
    async def synthesize(text):
        if text=='Second sentence.':
            playback.second_started.set()
            raise RuntimeError('Synthesis failed')
        async for pcm in original(text): yield pcm
    app._tts.synthesize_stream=synthesize
    task=asyncio.create_task(app._run_turn({'text':'explain','source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        await asyncio.wait_for(playback.second_started.wait(),1)
        assert app._spoken==''
        playback.first_release.set()
        await asyncio.wait_for(task,2)
        assert app._spoken.strip()=='First sentence.'
        assert playback.enqueued==[1]
        app._hermes.interrupt_response.assert_called_once_with(' First sentence.')
        app._hermes.complete_response.assert_not_called()
    finally:
        playback.first_release.set();task.cancel()
        await asyncio.gather(task,return_exceptions=True)


def test_context_budget_keeps_valid_json_and_whole_recent_memories(app):
    import json
    owner=app._memory.create_profile('Owner',consent=True)
    app._session_context.set_owner(owner.id)
    contents=[str(index)+'"\\'*999 for index in range(8)]
    for content in contents:
        app._memory.add_memory(owner.id,content,source='Explicit entry',consent=True)
    encoded=app._context_text()
    payload=json.loads(encoded)
    assert len(encoded)<=10000
    assert payload['scope']=='personal'
    assert payload['memories'][-1]['content']==contents[-1]
    assert all(item['content'] in contents for item in payload['memories'])


@pytest.mark.asyncio
async def test_enabling_microphone_after_text_start_loads_once_in_background(app):
    import threading
    entered=threading.Event();release=threading.Event()
    def start(): entered.set();release.wait(2)
    app._text_mode=True;app._mic_enabled=False
    app._stt.start=Mock(side_effect=start)
    app._broadcast_to_ui=AsyncMock()
    try:
        await asyncio.wait_for(app.handle_control({'type':'set_mic','enabled':True}),1)
        for _ in range(100):
            if entered.is_set(): break
            await asyncio.sleep(.005)
        assert entered.is_set()
        await app.handle_control({'type':'set_mic','enabled':True})
        assert app._stt.start.call_count==1
        release.set()
        await asyncio.wait_for(asyncio.gather(*app._tasks),2)
        assert app._settings()['voice_started']
        assert not app._settings()['voice_starting']
        await app.handle_control({'type':'set_mic','enabled':False})
        await app.handle_control({'type':'set_mic','enabled':True})
        assert app._stt.start.call_count==1
    finally:
        release.set()
        await asyncio.gather(*app._tasks,return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_voice_start_can_retry_from_microphone_toggle(app):
    app._stt.start=Mock(side_effect=[RuntimeError('model unavailable'),None])
    app._broadcast_to_ui=AsyncMock()
    await app.handle_control({'type':'set_mic','enabled':True})
    await asyncio.gather(*app._tasks)
    assert not app._mic_enabled and not app._voice_started and not app._voice_starting
    await app.handle_control({'type':'set_mic','enabled':True})
    await asyncio.gather(*app._tasks)
    assert app._voice_started and app._mic_enabled
    assert app._stt.start.call_count==2


def test_shared_context_budget_remains_valid_without_personal_memory(app):
    import json
    owner=app._memory.create_profile('Owner',consent=True)
    app._session_context.set_owner(owner.id)
    app._memory.add_memory(owner.id,'private marker',source='explicit',consent=True)
    app._session_context.mark_guest_present('g','Guest')
    for index in range(4): app._session_context.add_shared_note(str(index)+'"\\'*999)
    encoded=app._context_text()
    payload=json.loads(encoded)
    assert len(encoded)<=10000 and payload['scope']=='shared'
    assert payload['memories']==[] and 'private marker' not in encoded
    assert payload['shared_notes'][-1].startswith('3')


@pytest.mark.asyncio
async def test_barge_in_stops_reply_but_keeps_the_interrupting_utterance(app):
    import time as _time
    from types import SimpleNamespace
    app._barge_in=True;app._mic_enabled=True;app._current_status='speaking'
    app._cancel_turn=AsyncMock()
    event=lambda:SimpleNamespace(kind='speech_start',epoch=app._stt.epoch)
    app._speaking_since=_time.monotonic()  # inside the echo grace period
    await app._handle_speech_event(event())
    app._cancel_turn.assert_not_awaited()
    app._speaking_since=_time.monotonic()-1
    await app._handle_speech_event(event())
    app._cancel_turn.assert_awaited_once_with(keep_voice=True)
    app._barge_in=False;app._cancel_turn.reset_mock()
    await app._handle_speech_event(event())
    app._cancel_turn.assert_not_awaited()


def test_echo_cancel_routes_only_chassie_and_falls_back(monkeypatch):
    import echo_cancel
    calls=[]
    def pactl(*args,timeout=5):
        calls.append(args)
        return '42\n' if args[0]=='load-module' else ''
    monkeypatch.setattr(echo_cancel,'_pactl',pactl)
    monkeypatch.setattr(echo_cancel.shutil,'which',lambda name:'/usr/bin/pactl')
    monkeypatch.setattr(echo_cancel.atexit,'register',lambda f:None)
    monkeypatch.setenv('PULSE_SINK','unset');monkeypatch.setenv('PULSE_SOURCE','unset')  # restored after the test
    config={'conversation':{'barge_in':True},'audio':{'input_device':None,'output_device':None}}
    assert echo_cancel.enable(config)
    assert config['audio']['input_device']=='pulse' and config['audio']['output_device']=='pulse'
    assert echo_cancel.os.environ['PULSE_SINK']==echo_cancel.SINK
    assert any(a[0]=='load-module' and 'aec_method=webrtc' in a for a in calls)
    explicit={'conversation':{'barge_in':True},'audio':{'input_device':3}}
    assert not echo_cancel.enable(explicit) and explicit['conversation']['barge_in'] is False
    def broken(*args,timeout=5): raise echo_cancel.subprocess.CalledProcessError(1,'pactl')
    monkeypatch.setattr(echo_cancel,'_pactl',broken)
    failed={'conversation':{'barge_in':True},'audio':{}}
    assert not echo_cancel.enable(failed) and failed['conversation']['barge_in'] is False
