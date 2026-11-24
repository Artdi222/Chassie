"""Bounded, generation-aware PCM playback. Cancelling an utterance keeps the device alive."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import logging
import math
import threading

import numpy as np

logger = logging.getLogger('audio_player')

def keyframe_mouth(frames,t):
    """Linear interpolation of [seconds, openness] keyframes; closed outside them."""
    if not frames or t<=frames[0][0] or t>=frames[-1][0]: return 0.0
    lo,hi=0,len(frames)-1
    while hi-lo>1:
        mid=(lo+hi)//2
        if frames[mid][0]<=t: lo=mid
        else: hi=mid
    (t0,v0),(t1,v1)=frames[lo],frames[hi]
    return float(v0 if t1<=t0 else v0+(v1-v0)*(t-t0)/(t1-t0))


@dataclass
class _Utterance:
    generation: int
    done: threading.Event = field(default_factory=threading.Event)
    error: Exception | None = None
    ended: bool = False
    submitted_samples: int = 0

class AudioPlayer:
    def __init__(self, config, *, stream_factory=None):
        cfg=config['audio']
        self._sample_rate=cfg['output_sample_rate']
        self._output_device=cfg.get('output_device')
        self._block_size=max(1,int(self._sample_rate*.02))
        self._max_blocks=max(2,int(cfg.get('prebuffer_seconds',2)*self._sample_rate/self._block_size))
        self._factory=stream_factory
        self._condition=threading.Condition()
        self._io_lock=threading.Lock()
        self._queue=deque()
        self._generation=0
        self._current=None
        self._jobs={}
        self._running=False
        self._failure=None
        self._stream=None
        self._thread=None
        self._loop=None
        self._avatar=None
        self._analyzer=None
        self._effect_tasks=set()
        self._emotion_task=None

    def start(self, loop=None, avatar=None, analyzer=None):
        self._loop=loop
        self._avatar=avatar
        self._analyzer=analyzer
        self._running=True
        self._failure=None
        self._thread=threading.Thread(target=self._playback_loop,name='audio-player',daemon=True)
        self._thread.start()

    def begin_utterance(self):
        self.cancel_utterance()
        with self._condition:
            self._generation+=1
            job=_Utterance(self._generation)
            self._current=job
            self._jobs[job.generation]=job
            # Old completed jobs are only useful for diagnostics, not an unbounded history.
            for key in list(self._jobs)[:-64]:
                if self._jobs[key].done.is_set(): del self._jobs[key]
            if self._failure:
                job.error=self._failure; job.done.set()
            self._condition.notify_all()
            return job.generation

    def _cancel_locked(self):
        if self._current: self._current.done.set()
        self._queue.clear()
        self._current=None

    def cancel_utterance(self):
        with self._condition:
            cancelled=self._current
            needs_abort=cancelled is not None and not cancelled.done.is_set()
            self._cancel_locked()
            self._condition.notify_all()
        # Never hold the queue condition while waiting for a device operation.
        # Recheck under the same I/O lock in the writer to reject popped blocks.
        with self._io_lock:
            if self._stream and (needs_abort or not self._running):
                try:
                    self._stream.abort()
                    if self._running: self._stream.start()
                except Exception as exc:
                    self._failure=exc
        if self._loop:
            def cancel_effects():
                for task in list(self._effect_tasks):
                    if getattr(task,'utterance',None) is cancelled: task.cancel()
            try: self._loop.call_soon_threadsafe(cancel_effects)
            except RuntimeError: pass

    def clear_queue(self):
        self.cancel_utterance()

    async def enqueue(self, chunk, emotion=None, *, generation=None, mouth=None, mouth_offset=0):
        """Queue PCM; with mouth keyframes ([s, openness]) lip-sync follows the syllables, not loudness."""
        if generation is None:
            generation=self._current.generation if self._current else self.begin_utterance()
        audio=np.asarray(chunk,dtype=np.float32)
        if audio.ndim==2: audio=audio.mean(axis=1)
        if audio.ndim!=1 or not np.isfinite(audio).all(): raise ValueError('Invalid PCM audio')
        for offset in range(0,len(audio),self._block_size):
            block=audio[offset:offset+self._block_size].copy()
            while True:
                with self._condition:
                    if self._failure: raise RuntimeError('Audio output unavailable') from self._failure
                    job=self._current
                    if not self._running or not job or job.generation!=generation or job.ended: return False
                    if len(self._queue)<self._max_blocks:
                        lips=(mouth,(mouth_offset+offset)/self._sample_rate) if mouth else None
                        self._queue.append((job,block,emotion if offset==0 else None,lips))
                        self._condition.notify_all()
                        break
                await asyncio.sleep(.005)
        return True

    def mark_end(self,generation=None):
        with self._condition:
            if self._current and generation in (None,self._current.generation):
                self._current.ended=True
                self._condition.notify_all()

    async def wait_until_done(self,generation=None):
        job=self._jobs.get(generation) if generation is not None else self._current
        if not job: return
        while not job.done.is_set(): await asyncio.sleep(.005)
        if job.error: raise RuntimeError('Audio playback failed') from job.error

    def is_playing(self):
        with self._condition: return bool(self._current and not self._current.done.is_set())

    def heard_samples(self,generation):
        """Deprecated: submitted samples, not evidence of physical audibility."""
        return self.submitted_samples(generation)

    def submitted_samples(self,generation):
        job=self._jobs.get(generation)
        return job.submitted_samples if job else 0

    def _schedule_effect(self,job,emotion,mouth):
        if not self._avatar or not self._loop: return
        async def apply():
            if self._current is not job or job.done.is_set(): return
            if emotion: await self._avatar.trigger_emotion(emotion)
            if self._current is job and not job.done.is_set():
                await self._avatar.set_mouth_open(mouth)
        def schedule():
            if self._current is not job or job.done.is_set(): return
            # Boundary emotions have a separate slot, so slow mouth writes never
            # discard them. New emotion supersedes an older pending emotion.
            if emotion:
                if self._emotion_task and not self._emotion_task.done(): self._emotion_task.cancel()
            elif sum(not getattr(t,'is_emotion',False) for t in self._effect_tasks)>=2:
                return
            task=asyncio.create_task(apply())
            task.utterance=job
            task.is_emotion=bool(emotion)
            if emotion: self._emotion_task=task
            self._effect_tasks.add(task)
            task.add_done_callback(self._effect_done)
        try: self._loop.call_soon_threadsafe(schedule)
        except RuntimeError: pass

    async def flush_effects(self):
        """Cancel/await old avatar writes before the caller resets neutral/mouth."""
        tasks=[task for task in self._effect_tasks
               if getattr(task,'utterance',None) is not self._current]
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)

    def _effect_done(self,task):
        self._effect_tasks.discard(task)
        if not task.cancelled():
            try: task.result()
            except Exception: logger.debug('Avatar update unavailable')

    def _playback_loop(self):
        try:
            factory=self._factory
            if factory is None:
                import sounddevice as sd
                factory=sd.OutputStream
            stream=factory(samplerate=self._sample_rate,blocksize=self._block_size,
                           channels=1,dtype='float32',device=self._output_device)
            with self._io_lock:
                self._stream=stream
                stream.start()
            while self._running:
                drain=None
                with self._condition:
                    while self._running and not self._queue:
                        if self._current and self._current.ended and not self._current.done.is_set():
                            drain=self._current
                            break
                        self._condition.wait(.02)
                    if not self._running: break
                    if drain is None:
                        job,block,emotion,lips=self._queue.popleft()
                        self._condition.notify_all()
                        if self._current is not job: continue
                if drain is not None:
                    # Some ALSA/PipeWire hosts return from stop() immediately,
                    # discarding their remaining device buffer. Push silence
                    # through the reported output latency first so only silence
                    # remains when stopping. Release the I/O lock every block
                    # so an explicit Stop can still interrupt this drain.
                    latency=getattr(stream,'latency',0.0)
                    if not isinstance(latency,(int,float)) or not math.isfinite(latency) or latency<0:
                        raise RuntimeError('Invalid audio output latency')
                    padding=math.ceil(latency*self._sample_rate/self._block_size)+1 if latency else 0
                    silence=np.zeros((self._block_size,1),dtype=np.float32)
                    for _ in range(padding):
                        with self._io_lock:
                            if self._current is not drain or not self._running: break
                            stream.write(silence)
                    with self._io_lock:
                        if self._current is not drain: continue
                        # Finish the host drain as well; accepted writes alone
                        # do not mean the device has played the final samples.
                        stream.stop()
                        if self._running: stream.start()
                        with self._condition:
                            if self._current is drain: drain.done.set()
                    continue
                if self._current is not job: continue
                if lips:
                    # What the listener hears now was written one output latency ago.
                    latency=getattr(stream,'latency',0.0)
                    latency=latency if isinstance(latency,(int,float)) and math.isfinite(latency) else 0.0
                    mouth=keyframe_mouth(lips[0],lips[1]+len(block)/2/self._sample_rate-min(latency,.25))
                else:
                    mouth=self._analyzer.analyze_chunk(block) if self._analyzer else 0
                with self._io_lock:
                    if self._current is not job or not self._running: continue
                    self._schedule_effect(job,emotion,mouth)
                    stream.write(block.reshape(-1,1))
                    job.submitted_samples+=len(block)
        except Exception as exc:
            logger.warning('Audio output unavailable: %s',type(exc).__name__)
            with self._condition:
                self._failure=exc
                if self._current:
                    self._current.error=exc; self._current.done.set()
                self._queue.clear()
                self._condition.notify_all()
        finally:
            with self._io_lock:
                if self._stream:
                    try:
                        try: self._stream.abort()
                        finally: self._stream.close()
                    except Exception: pass
                self._stream=None

    def stop(self):
        self._running=False
        self.cancel_utterance()
        if self._thread: self._thread.join(timeout=2)
        for task in list(self._effect_tasks):
            if self._loop: self._loop.call_soon_threadsafe(task.cancel)
