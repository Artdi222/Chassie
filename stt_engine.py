"""Bounded microphone capture and transcription workers with mute epochs."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
from pathlib import Path
import queue
import threading
import time

import numpy as np

_CUDA_LIBRARIES=('cublas/lib/libcublasLt.so.12','cublas/lib/libcublas.so.12','cudnn/lib/libcudnn.so.9')


def preload_cuda_libraries():
    """Expose pip-installed cuBLAS/cuDNN to CTranslate2 without changing LD_LIBRARY_PATH."""
    import ctypes
    import importlib.util
    spec=importlib.util.find_spec('nvidia')
    if spec is None or not spec.submodule_search_locations: return
    root=Path(next(iter(spec.submodule_search_locations)))
    for library in _CUDA_LIBRARIES:
        if (root/library).is_file(): ctypes.CDLL(str(root/library),mode=ctypes.RTLD_GLOBAL)

logger=logging.getLogger('stt')

@dataclass(frozen=True)
class Utterance:
    pcm: bytes
    started_at: float
    ended_at: float

@dataclass(frozen=True)
class SpeechEvent:
    kind: str
    epoch: int
    started_at: float
    ended_at: float
    text: str = ''
    speaker: dict | None = None

class SpeechSegmenter:
    # A short gap after real speech is where a listener nods ("mm"), before the utterance ends.
    PAUSE_SECONDS=.3
    PAUSE_AFTER_SPEECH=1.0

    def __init__(self, *, sample_rate=16000,silence_duration=.8,min_speech_duration=.09,
                 max_speech_duration=15,pre_roll=.18):
        self.sample_rate=sample_rate
        self.silence_duration=silence_duration
        self.minimum=min_speech_duration
        self.maximum=max_speech_duration
        self._pre=deque(maxlen=max(1,int(pre_roll/.03)))
        self._frames=[]
        self._started=None
        self._last_voice=None
        self._voiced=0
        self._paused=False

    def feed(self,frame,speech,now):
        events=[]
        duration=len(frame)/(2*self.sample_rate)
        if self._started is None:
            if not speech:
                self._pre.append(frame); return events
            self._started=now-sum(map(len,self._pre))/(2*self.sample_rate)
            self._frames=list(self._pre); self._pre.clear()
            events.append(('speech_start',now))
        self._frames.append(frame)
        if speech: self._last_voice=now; self._voiced+=duration; self._paused=False
        elif (not self._paused and self._last_voice is not None and self._voiced>=self.PAUSE_AFTER_SPEECH
              and self.PAUSE_SECONDS<=now-self._last_voice<self.silence_duration):
            self._paused=True
            events.append(('speech_pause',now))
        elapsed=sum(map(len,self._frames))/(2*self.sample_rate)
        if (not speech and self._last_voice is not None and now-self._last_voice>=self.silence_duration) or elapsed>=self.maximum:
            if self._voiced>=self.minimum:
                events.append(('utterance',Utterance(b''.join(self._frames),self._started,now+duration)))
            self._frames=[]; self._started=None; self._last_voice=None; self._voiced=0; self._paused=False
        return events

class STTEngine:
    def __init__(self,config,output_queue,*,model_factory=None,stream_factory=None):
        self._config=config
        self._cfg=config['stt']
        self._rate=config['audio']['sample_rate']
        if self._rate not in (8000,16000,32000,48000): raise ValueError('Unsupported VAD sample rate')
        self._output_queue=output_queue
        self._jobs=queue.Queue(maxsize=3)
        self._lock=threading.RLock()
        self._stream_lock=threading.RLock()
        self._wake=threading.Event()
        self._running=False
        self._starting=False
        self._lifecycle_revision=0
        self._muted=False
        self._epoch=0
        self._model=None
        self._model_factory=model_factory
        self._stream_factory=stream_factory
        self._stream=None
        self._threads=[]
        self.error=None
        self.dropped_utterances=0
        self.speaker_identity=None

    @property
    def epoch(self):
        with self._lock: return self._epoch

    @property
    def muted(self):
        with self._lock: return self._muted

    def start(self):
        with self._lock:
            if self._running or self._starting or any(t.is_alive() for t in self._threads): return
            self._starting=True
            lifecycle=self._lifecycle_revision
        try:
            factory=self._model_factory
            if factory is None:
                from faster_whisper import WhisperModel
                factory=WhisperModel
            model=self._load_model(factory)
            with self._lock:
                # Cancelling asyncio.to_thread does not cancel a native model
                # constructor. A shutdown during loading must remain terminal
                # for this start attempt when the constructor eventually returns.
                if lifecycle!=self._lifecycle_revision: return
                self._model=model
                self._running=True
                self._threads=[]
                for target,name in ((self._capture_loop,'mic-capture'),(self._transcribe_loop,'speech-transcriber')):
                    t=threading.Thread(target=target,name=name,daemon=True)
                    self._threads.append(t); t.start()
        finally:
            with self._lock: self._starting=False

    def _load_model(self,factory):
        device=self._cfg.get('device','cpu')
        threads=self._cfg.get('cpu_threads',2)
        if device=='cuda':
            try:
                preload_cuda_libraries()
                model=factory(self._cfg.get('model','base'),device='cuda',
                              compute_type=self._cfg.get('compute_type','int8_float16'),cpu_threads=threads)
                # Missing cuBLAS/cuDNN only fails on the first encode, not on construction.
                list(model.transcribe(np.zeros(16000,dtype=np.float32),beam_size=1)[0])
                self.device='cuda'
                return model
            except Exception as exc:
                logger.warning('GPU speech recognition unavailable (%s); using CPU',type(exc).__name__)
        self.device='cpu'
        return factory(self._cfg.get('cpu_model',self._cfg.get('model','base')) if device=='cuda' else self._cfg.get('model','base'),
                       device='cpu',compute_type='int8' if device=='cuda' else self._cfg.get('compute_type','int8'),cpu_threads=threads)

    def invalidate(self):
        with self._lock:
            self._epoch+=1
            for q in (self._jobs,self._output_queue):
                while True:
                    try: q.get_nowait()
                    except queue.Empty: break

    def set_muted(self,muted):
        """Mute without touching the device from this thread.

        Aborting a PortAudio/ALSA stream while the capture thread is inside read()
        crashed the whole process (core dump in pa_linux_alsa.c), and waiting for the
        stream lock froze the mic switch. The capture thread closes its own stream
        within one 30 ms block; audio read meanwhile is dropped by the _muted checks.
        """
        with self._lock:
            if self._muted==muted: return
            self._muted=muted
            self.invalidate()
        self._wake.set()

    def publish_transcript(self,text,epoch,start,end,speaker=None):
        with self._lock:
            if self._muted or epoch!=self._epoch: return False
            try: self._output_queue.put_nowait(SpeechEvent('transcript',epoch,start,end,text,speaker))
            except queue.Full:
                self.dropped_utterances+=1; return False
            return True

    def _publish_start(self,epoch,now,kind='speech_start'):
        with self._lock:
            if self._muted or epoch!=self._epoch: return
            try: self._output_queue.put_nowait(SpeechEvent(kind,epoch,now,now))
            except queue.Full: pass

    def _capture_loop(self):
        import webrtcvad
        vad=webrtcvad.Vad(self._cfg.get('vad_aggressiveness',2))
        while self._running:
            if self.muted:
                self._wake.wait(.1); self._wake.clear(); continue
            epoch=self.epoch
            segmenter=SpeechSegmenter(sample_rate=self._rate,
                silence_duration=self._cfg.get('silence_duration',.8),
                min_speech_duration=self._cfg.get('min_speech_duration',.09),
                max_speech_duration=self._cfg.get('max_speech_duration',15))
            stream=None
            try:
                factory=self._stream_factory
                if factory is None:
                    import sounddevice as sd
                    factory=sd.RawInputStream
                with self._stream_lock:
                    with self._lock:
                        cancelled=self._muted or epoch!=self._epoch or not self._running
                    if cancelled: continue
                    stream=factory(samplerate=self._rate,blocksize=int(self._rate*.03),dtype='int16',channels=1,
                                   device=self._config['audio'].get('input_device'))
                    with self._lock: self._stream=stream
                    stream.start()
                self.error=None
                while self._running and not self.muted and epoch==self.epoch:
                    data,overflow=stream.read(int(self._rate*.03))
                    if overflow:
                        self.dropped_utterances+=1
                        # Discontinuous audio must not be merged into an invented utterance.
                        break
                    frame=bytes(data); now=time.monotonic()
                    for kind,value in segmenter.feed(frame,vad.is_speech(frame,self._rate),now):
                        if kind in ('speech_start','speech_pause'): self._publish_start(epoch,value,kind)
                        else:
                            with self._lock:
                                if self._muted or epoch!=self._epoch: continue
                                try: self._jobs.put_nowait((epoch,value))
                                except queue.Full: self.dropped_utterances+=1
            except Exception as exc:
                if not self.muted and self._running:
                    self.error=f'Microphone unavailable ({type(exc).__name__})'
                    logger.warning(self.error)
                    self._wake.wait(1); self._wake.clear()
            finally:
                with self._stream_lock:
                    if stream is not None and self._stream is stream:
                        try:
                            try: stream.abort()
                            finally: stream.close()
                        except Exception: pass
                        finally:
                            with self._lock: self._stream=None

    def _transcribe_loop(self):
        while self._running:
            try: epoch,utterance=self._jobs.get(timeout=.1)
            except queue.Empty: continue
            if self.muted or epoch!=self.epoch: continue
            audio=np.frombuffer(utterance.pcm,dtype=np.int16).astype(np.float32)/32768
            text=self._transcribe(audio)
            speaker=(self.speaker_identity.process(audio,self._rate,active=lambda:not self.muted and epoch==self.epoch)
                     if text and self.speaker_identity else None)
            if text:self.publish_transcript(text,epoch,utterance.started_at,utterance.ended_at,speaker)

    def _transcribe(self,audio):
        try:
            segments,_=self._model.transcribe(audio,beam_size=self._cfg.get('beam_size',3),
                language=self._cfg.get('language'),vad_filter=True)
            texts=[s.text.strip() for s in segments if s.avg_logprob>=-1 and s.no_speech_prob<=.6]
            return ' '.join(texts).strip() or None
        except Exception as exc:
            self.error=f'Transcription unavailable ({type(exc).__name__})'
            logger.warning(self.error)
            return None

    def is_listening(self):
        return self._running and not self.muted and self._stream is not None

    def stop(self):
        with self._lock:
            self._lifecycle_revision+=1
            self._running=False
            threads=tuple(self._threads)
        self.set_muted(True)
        self._wake.set()
        for thread in threads: thread.join(timeout=2)
