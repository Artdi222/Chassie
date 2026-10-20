"""VOICEVOX speech, decoded to bounded mono PCM."""
from __future__ import annotations
import asyncio
import io
import re

import numpy as np


def sentence_chunks(text, max_chars=350):
    """Split completed text; this does not imply Hermes token streaming."""
    text=text.strip()
    if not text: return []
    # Protect common abbreviations and decimal points before boundary detection.
    protected=re.sub(r'(?<=\d)\.(?=\d)', '\ufff0', text)
    protected=re.sub(r'\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|vs|etc)\.',lambda m:m[0][:-1]+'\ufff0',protected,flags=re.I)
    sentences=re.split(r'(?<=[.!?])\s+',protected)
    chunks=[]
    for sentence in sentences:
        sentence=sentence.replace('\ufff0','.')
        while len(sentence)>max_chars:
            cut=sentence.rfind(' ',0,max_chars+1)
            if cut<1: cut=max_chars
            chunks.append(sentence[:cut]); sentence=sentence[cut:].strip()
        if sentence: chunks.append(sentence)
    return chunks

class TTSEngine:
    def __init__(self,config):
        cfg=config['tts']
        if cfg.get('engine','voicevox')!='voicevox': raise ValueError('Unknown TTS engine; only VOICEVOX is supported')
        self.engine='voicevox'
        from voicevox_tts import VoicevoxTTS
        self._voicevox=VoicevoxTTS(config)
        self._sample_rate=cfg['sample_rate']
        self._max_samples=int(cfg.get('max_audio_seconds',60)*self._sample_rate)
        if self._max_samples<=0: raise ValueError('max_audio_seconds must be positive')
        self._ready=False

    def load_model(self):
        self._voicevox.check_installation()
        import av  # noqa: F401
        self._ready=True

    def start(self): pass

    def begin_turn(self): pass

    def status(self):
        return {'selected':self.engine,'active':self.engine,'ready':self._ready,'reason':None}

    async def synthesize_stream(self,text,*,emotion='neutral'):
        if not self._ready: raise RuntimeError('TTS not initialized')
        if not text or not text.strip(): return
        try:
            data=await self._voicevox.synthesize(text,emotion)
            audio=await asyncio.to_thread(self._decode,data)
        except asyncio.CancelledError: raise
        except Exception as exc: raise RuntimeError('Speech synthesis failed; the text is still available.') from exc
        if not len(audio): raise RuntimeError('TTS decoded no audio')
        yield audio

    def _decode(self,data):
        import av
        resampler=av.AudioResampler(format='flt',layout='mono',rate=self._sample_rate)
        blocks=[]
        samples=0
        def append(frame):
            nonlocal samples
            samples+=frame.samples
            if samples>self._max_samples: raise RuntimeError('Decoded TTS audio exceeds duration limit')
            blocks.append(frame.to_ndarray().reshape(-1))
        with av.open(io.BytesIO(data)) as container:
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame): append(converted)
            for converted in resampler.resample(None): append(converted)
        return np.concatenate(blocks).astype(np.float32) if blocks else np.zeros(0,dtype=np.float32)

    async def close(self):
        await self._voicevox.close()
        self._ready=False

    def is_ready(self): return self._ready
