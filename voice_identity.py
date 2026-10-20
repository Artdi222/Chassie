"""Consensual local speaker hints. Raw samples are never saved or transmitted."""
from pathlib import Path
import threading
import time
import numpy as np

MODEL=Path(__file__).parent/'.chassie/speaker-models/wespeaker_en_voxceleb_resnet34.onnx'


def match_voice(feature,templates,threshold=.7,margin=.12):
    feature=np.asarray(feature,dtype=np.float32)
    if feature.shape!=(256,) or not np.isfinite(feature).all() or np.linalg.norm(feature)<1e-6:return None
    scores=[]
    for item in templates:
        ref=np.asarray(item['embedding'],dtype=np.float32)
        if ref.shape!=feature.shape or not np.isfinite(ref).all():continue
        denominator=np.linalg.norm(feature)*np.linalg.norm(ref)
        if denominator>1e-6:scores.append((float(feature@ref/denominator),item))
    scores.sort(key=lambda p:p[0],reverse=True)
    if not scores or scores[0][0]<threshold or (len(scores)>1 and scores[0][0]-scores[1][0]<margin):return None
    score,item=scores[0]
    return {'profile_id':item['profile_id'],'name':item['name'],'similarity':round(score,3)}


class VoiceIdentity:
    def __init__(self,memory,*,model_path=MODEL,extractor=None,presence=None,clock=time.monotonic):
        self.memory=memory;self.path=Path(model_path);self.extractor=extractor
        self.presence=presence;self.clock=clock;self.pending=None
        self._lock=threading.RLock();self.error=None;self.last=None

    @property
    def ready(self):return self.extractor is not None or self.path.is_file()

    @property
    def enrolling(self):
        with self._lock:
            if self.pending and self.clock()>self.pending[1]:self.pending=None
            return self.pending is not None

    def enroll(self,profile_id,*,consent):
        if consent is not True:raise ValueError('The speaker must agree to voice recognition')
        if not self.ready:raise ValueError('Voice recognition is unavailable. Run scripts/install_speaker.py.')
        with self._lock:self.pending=(profile_id,self.clock()+90);self.last=None

    def cancel(self):
        with self._lock:self.pending=None;self.last=None

    def _embedding(self,audio,rate):
        if self.extractor is None:
            import sherpa_onnx
            cfg=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.path),num_threads=2,provider='cpu')
            if not cfg.validate():raise ValueError('Invalid speaker model')
            self.extractor=sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        stream=self.extractor.create_stream()
        stream.accept_waveform(sample_rate=rate,waveform=audio)
        stream.input_finished()
        if not self.extractor.is_ready(stream):return None
        return np.asarray(self.extractor.compute(stream),dtype=np.float32)

    def process(self,audio,rate,*,active=lambda:True):
        with self._lock:
            if self.pending and self.clock()>self.pending[1]:self.pending=None
            pending=self.pending
        templates=self.memory.list_voices()
        if not pending and not templates:return None
        if not active():return None
        if not pending:self.last={'match':None,'at':self.clock()}
        if len(audio)<rate*(3 if pending else 1.5) or not np.isfinite(audio).all() or np.sqrt(np.mean(audio**2))<.008:
            return {'enrollment':'Speak alone for at least 3 seconds.'} if pending else {'match':None}
        if pending and self.presence:
            status=self.presence()
            if status.get('identity',{}).get('face_count',0)>1:
                return {'enrollment':'Only the consenting speaker should be in front of the camera.'}
        try:
            feature=self._embedding(np.ascontiguousarray(audio[:rate*12],dtype=np.float32),rate)
            if not active():return None
            if feature is None:return {'enrollment':'Speak clearly for at least 3 seconds.'} if pending else {'match':None}
            if pending:
                with self._lock:
                    if self.pending!=pending or self.clock()>pending[1]:return None
                    self.memory.save_voice(pending[0],feature.tolist(),consent=True)
                    self.pending=None
                return {'enrollment':'Voice saved locally. Recognition is now automatic.','saved':True}
            hint=match_voice(feature,templates)
            self.last={'match':hint,'at':self.clock()}
            return {'match':hint}
        except Exception as exc:
            self.error=f'Voice recognition unavailable ({type(exc).__name__})'
            return {'enrollment':self.error} if pending else {'match':None}
