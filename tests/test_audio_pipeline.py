import asyncio
import queue
import threading
import time

import numpy as np
import pytest

from audio_player import AudioPlayer
from audio_analyzer import AudioAnalyzer
from stt_engine import STTEngine, SpeechSegmenter

CONFIG = {'audio': {'sample_rate':16000,'output_sample_rate':24000},
          'stt': {'model':'base','device':'cpu','silence_duration':0.12,'min_speech_duration':0.06}}


def test_real_analyzer_values_survive_json_and_drive_desktop_mouth():
    import json
    from desktop.state import OverlayState
    analyzer = AudioAnalyzer()
    state = OverlayState()
    levels = []
    for pcm in (np.ones(480, dtype=np.float32) * .2, *[np.zeros(480, dtype=np.float32) for _ in range(8)]):
        value = analyzer.analyze_chunk(pcm)
        assert type(value) is float
        event = json.loads(json.dumps({'type': 'avatar_state', 'generation': 1, 'emotion': 'neutral', 'mouth': value, 'status': 'speaking'}))
        assert state.receive(event, now=1)
        levels.append(state.mouth_at(1))
    assert levels[0] > .5 and levels[-1] < .001

class FakeStream:
    def __init__(self, **kwargs):
        self.blocks=[]
        self.started=threading.Event()
        self.release=threading.Event()
        self.closed=False
    def start(self): pass
    def write(self, data):
        self.blocks.append(data.copy())
        self.started.set()
        self.release.wait(0.1)
    def stop(self): pass
    def abort(self): self.release.set()
    def close(self): self.closed=True

async def eventually(predicate):
    for _ in range(200):
        if predicate(): return
        await asyncio.sleep(.005)
    assert predicate()

@pytest.mark.asyncio
async def test_cancel_drops_buffer_and_old_generation_but_player_reusable():
    stream=FakeStream()
    player=AudioPlayer(CONFIG, stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop())
    first=player.begin_utterance()
    await player.enqueue(np.ones(24000), generation=first)
    await eventually(stream.started.is_set)
    player.cancel_utterance()
    stream.release.set()
    assert not await player.enqueue(np.ones(1200),generation=first)
    second=player.begin_utterance()
    assert await player.enqueue(np.full(1200,0.25),generation=second)
    player.mark_end(second)
    await asyncio.wait_for(player.wait_until_done(second),1)
    assert len(stream.blocks)<20
    assert np.allclose(stream.blocks[-1],.25)
    player.stop()

@pytest.mark.asyncio
async def test_end_before_worker_consumes_first_chunk_completes():
    stream=FakeStream(); stream.release.set()
    player=AudioPlayer(CONFIG,stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop())
    gen=player.begin_utterance()
    await player.enqueue(np.ones(51),generation=gen)
    player.mark_end(gen)
    await asyncio.wait_for(player.wait_until_done(gen),1)
    assert len(stream.blocks)==1
    player.stop()

@pytest.mark.asyncio
async def test_playback_failure_releases_waiter_and_reports_error():
    def broken(**kw): raise RuntimeError('missing output device')
    player=AudioPlayer(CONFIG,stream_factory=broken)
    player.start(asyncio.get_running_loop())
    gen=player.begin_utterance()
    with pytest.raises(RuntimeError):
        await player.enqueue(np.ones(1200),generation=gen)
        player.mark_end(gen)
        await asyncio.wait_for(player.wait_until_done(gen),1)
    player.stop()


@pytest.mark.asyncio
async def test_cancel_between_analyzer_and_write_rejects_popped_block():
    stream=FakeStream(); stream.release.set()
    class Analyzer:
        entered=threading.Event()
        release=threading.Event()
        def analyze_chunk(self,block):
            self.entered.set()
            self.release.wait(1)
            return 0
    analyzer=Analyzer()
    player=AudioPlayer(CONFIG,stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop(),analyzer=analyzer)
    generation=player.begin_utterance()
    await player.enqueue(np.ones(480),generation=generation)
    await eventually(analyzer.entered.is_set)
    player.cancel_utterance()
    analyzer.release.set()
    await asyncio.sleep(.03)
    assert stream.blocks == []
    player.stop()


@pytest.mark.asyncio
async def test_completion_waits_for_physical_drain_and_cancel_discards_device_buffer():
    class BufferedStream(FakeStream):
        def __init__(self):
            super().__init__(); self.buffer=[]; self.audible=[]
            self.draining=threading.Event(); self.drain_release=threading.Event()
        def write(self,data): self.buffer.append(data.copy()); self.started.set()
        def abort(self): self.buffer.clear()
        def stop(self):
            self.draining.set(); self.drain_release.wait(1)
            self.audible.extend(self.buffer); self.buffer.clear()
    stream=BufferedStream()
    player=AudioPlayer(CONFIG,stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop())
    first=player.begin_utterance()
    await player.enqueue(np.ones(480),generation=first)
    await eventually(stream.started.is_set)
    player.cancel_utterance()
    assert not stream.buffer and not stream.audible
    second=player.begin_utterance()
    await player.enqueue(np.full(480,.25),generation=second)
    player.mark_end(second)
    done=asyncio.create_task(player.wait_until_done(second))
    await eventually(stream.draining.is_set)
    assert not done.done()
    stream.drain_release.set()
    await asyncio.wait_for(done,1)
    assert len(stream.audible)==1 and np.allclose(stream.audible[0],.25)
    player.stop()


@pytest.mark.asyncio
async def test_bounded_enqueue_unblocks_after_cancellation():
    stream=FakeStream()
    player=AudioPlayer({'audio':{'output_sample_rate':24000,'prebuffer_seconds':.04}},
                       stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop())
    generation=player.begin_utterance()
    pending=asyncio.create_task(player.enqueue(np.ones(24000),generation=generation))
    await eventually(stream.started.is_set)
    assert len(player._queue)<=2
    cancelled=threading.Event()
    def cancel():
        player.cancel_utterance(); cancelled.set()
    worker=threading.Thread(target=cancel)
    worker.start()
    await eventually(cancelled.is_set)
    worker.join(1)
    assert not await asyncio.wait_for(pending,1)
    player.stop()

def test_segmenter_preserves_preroll_short_speech_and_caps_continuous_speech():
    seg=SpeechSegmenter(sample_rate=16000,silence_duration=.09,min_speech_duration=.03,max_speech_duration=.18)
    quiet=b'\x00'*960
    loud=b'\x01'*960
    seg.feed(quiet,False,0)
    events=seg.feed(loud,True,.03)
    assert events[0][0]=='speech_start'
    events=[]
    for i in range(2,12): events+=seg.feed(loud,True,i*.03)
    utterances=[e[1] for e in events if e[0]=='utterance']
    assert utterances and utterances[0].pcm.startswith(quiet)
    assert len(utterances[0].pcm)<=int(16000*2*.5)

def test_muting_invalidates_inflight_transcription():
    outputs=queue.Queue()
    stt=STTEngine(CONFIG,outputs)
    epoch=stt.epoch
    stt.set_muted(True)
    assert stt.muted
    assert stt.epoch>epoch
    assert not stt.publish_transcript('old audio',epoch,0,1)
    stt.set_muted(False)
    assert not stt.publish_transcript('still old',epoch,0,1)
    assert stt.publish_transcript('yes',stt.epoch,2,3)
    assert outputs.get_nowait().text=='yes'


def wait_thread(predicate, timeout=1):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline: time.sleep(.005)
    assert predicate()


def test_capture_continues_during_transcription_and_mute_closes_device(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'webrtcvad',SimpleNamespace(Vad=lambda value:SimpleNamespace(is_speech=lambda frame,rate: True)))
    entered=threading.Event(); release=threading.Event()
    class Model:
        def transcribe(self,*args,**kwargs):
            entered.set(); release.wait(2)
            return [SimpleNamespace(text='late output',avg_logprob=0,no_speech_prob=0)],None
    class Input:
        def __init__(self): self.reads=0; self.closed=False
        def start(self): pass
        def read(self,count):
            time.sleep(.002); self.reads+=1
            if self.closed: raise RuntimeError('closed')
            return b'\x01'*960,False
        def abort(self): raise RuntimeError('device abort failed')
        def close(self): self.closed=True
    stream=Input(); outputs=queue.Queue()
    config={'audio':CONFIG['audio'], 'stt':{**CONFIG['stt'],'max_speech_duration':.06}}
    engine=STTEngine(config,outputs,model_factory=lambda *a,**kw:Model(),stream_factory=lambda **kw:stream)
    engine.start()
    try:
        wait_thread(entered.is_set)
        before=stream.reads
        wait_thread(lambda:stream.reads>before+3)
        engine.set_muted(True)  # Returns at once; the capture thread closes its own stream.
        wait_thread(lambda:stream.closed and not engine.is_listening())
        after=stream.reads
        release.set()
        time.sleep(.04)
        assert stream.reads<=after+1
        assert outputs.empty()
    finally:
        release.set(); engine.stop()


def test_mute_never_blocks_on_a_slow_device_open_and_closes_it_after(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'webrtcvad',SimpleNamespace(Vad=lambda value:SimpleNamespace(is_speech=lambda frame,rate: False)))
    constructing=threading.Event(); release=threading.Event()
    class Input:
        closed=False
        def start(self): pass
        def read(self,count): time.sleep(.002); return b'\0'*960,False
        def abort(self): raise AssertionError('mute must not abort the device from another thread')
        def close(self): self.closed=True
    streams=[]
    def factory(**kwargs):
        constructing.set(); release.wait(1)
        stream=Input(); streams.append(stream); return stream
    engine=STTEngine(CONFIG,queue.Queue(),model_factory=lambda *a,**kw:object(),stream_factory=factory)
    engine.start(); wait_thread(constructing.is_set)
    try:
        started=time.monotonic(); engine.set_muted(True)
        assert time.monotonic()-started<.05  # The mic switch never waits for the device.
        release.set()
        wait_thread(lambda:streams and all(stream.closed for stream in streams))
        count=len(streams); time.sleep(.03)
        assert len(streams)==count and not engine.is_listening()
    finally:
        release.set(); engine.stop()


def test_stop_during_model_load_prevents_late_capture_start():
    loading=threading.Event(); release=threading.Event()
    captures=[]
    def load(*args,**kwargs):
        loading.set(); release.wait(2); return object()
    engine=STTEngine(CONFIG,queue.Queue(),model_factory=load,
                     stream_factory=lambda **kwargs:captures.append('opened'))
    starter=threading.Thread(target=engine.start)
    starter.start()
    try:
        wait_thread(loading.is_set)
        engine.stop()
        release.set(); starter.join(1)
        assert not starter.is_alive()
        assert not engine._running
        assert not engine._threads
        assert not captures
        assert engine.muted
    finally:
        release.set(); starter.join(1); engine.stop()

@pytest.mark.asyncio
async def test_host_stop_that_drops_tail_cannot_cut_off_sentence():
    class HostStream(FakeStream):
        # Model the observed PipeWire/ALSA host: stop returns immediately and
        # discards the device tail even though write accepted all the samples.
        latency = .04
        def __init__(self):
            super().__init__();self.pending=np.zeros(0);self.audible=[];self.aborts=0
        def write(self,data):
            self.pending=np.concatenate((self.pending,data.reshape(-1)))
            count=max(0,len(self.pending)-960)
            self.audible.extend(self.pending[:count]);self.pending=self.pending[count:]
        def stop(self): self.pending=np.zeros(0)
        def abort(self): self.aborts+=1;self.pending=np.zeros(0)
    stream=HostStream();player=AudioPlayer(CONFIG,stream_factory=lambda **kw:stream)
    player.start(asyncio.get_running_loop())
    try:
        first=player.begin_utterance()
        await player.enqueue(np.full(2400,.25),generation=first);player.mark_end(first)
        await asyncio.wait_for(player.wait_until_done(first),1)
        assert np.count_nonzero(np.asarray(stream.audible)==.25)==2400
        aborts=stream.aborts
        second=player.begin_utterance()
        assert stream.aborts==aborts, 'Completed sentence must not be aborted at the next boundary'
        await player.enqueue(np.full(2400,.5),generation=second);player.mark_end(second)
        await asyncio.wait_for(player.wait_until_done(second),1)
        audible=np.asarray(stream.audible)
        assert np.count_nonzero(audible==.5)==2400
        assert np.max(np.where(audible==.25))<np.min(np.where(audible==.5))
    finally: player.stop()


def test_gpu_speech_model_falls_back_to_cpu_when_cuda_fails_on_first_encode(monkeypatch):
    import stt_engine
    monkeypatch.setattr(stt_engine, 'preload_cuda_libraries', lambda: None)
    calls = []
    class Model:
        def __init__(self, name, device, compute_type, cpu_threads):
            calls.append((name, device, compute_type))
            self.device = device
        def transcribe(self, audio, **kw):
            if self.device == 'cuda': raise RuntimeError('Library libcublas.so.12 is not found')
            return iter(()), None
    config = {**CONFIG, 'stt': {**CONFIG['stt'], 'device': 'cuda', 'model': 'small', 'cpu_model': 'base'}}
    engine = STTEngine(config, queue.Queue(), model_factory=Model)
    model = engine._load_model(Model)
    assert calls == [('small', 'cuda', 'int8_float16'), ('base', 'cpu', 'int8')]
    assert model.device == 'cpu' and engine.device == 'cpu'
    calls.clear()
    Model.transcribe = lambda self, audio, **kw: (iter(()), None)
    assert engine._load_model(Model).device == 'cuda' and engine.device == 'cuda'
    assert calls == [('small', 'cuda', 'int8_float16')]
