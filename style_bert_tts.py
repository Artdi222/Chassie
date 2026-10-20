"""Owned expressive speech worker with bounded latency and retained VOICEVOX."""
from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from bilingual import JAPANESE
from voicevox_tts import VoicevoxTTS

ROOT=Path(__file__).resolve().parent
logger=logging.getLogger('style_bert_tts')


def style_for_emotion(emotion):
    if emotion in ('happy','excited','teasing'):return 'るんるん',.8
    if emotion in ('sleepy','sad','concerned','defeated'):return 'よふかし',.7
    if emotion in ('shy','love'):return 'ささやきB（有声）',.6
    return 'Neutral',.8


class StyleBertTTS:
    def __init__(self,config):
        cfg=config['tts'];self.device=cfg.get('style_bert_device','cpu')
        default_root='.chassie/style-bert/cpu' if self.device=='cpu' else '.chassie/style-bert'
        self.root=Path(cfg.get('style_bert_dir',default_root)).expanduser()
        if not self.root.is_absolute():self.root=ROOT/self.root
        voicevox_root=Path(cfg.get('voicevox_dir','.chassie/voicevox')).expanduser()
        if not voicevox_root.is_absolute():voicevox_root=ROOT/voicevox_root
        self.dictionary=voicevox_root/'dict/open_jtalk_dic_utf_8-1.11'
        self.timeout=float(cfg.get('style_bert_timeout',30));self.load_timeout=float(cfg.get('style_bert_load_timeout',120))
        if not .1<=self.timeout<=30 or not 1<=self.load_timeout<=300:raise ValueError('Invalid speech worker timeout')
        self.threads=cfg.get('style_bert_threads',cfg.get('cpu_threads',2))
        if self.device not in ('cuda','cpu') or type(self.threads) is not int or not 1<=self.threads<=8:raise ValueError('Invalid speech worker device or threads')
        self._process=None;self._lock=asyncio.Lock();self._ready=False;self.last_metrics={}

    @property
    def ready(self):return bool(self._ready and self._process and self._process.returncode is None)

    def check_installation(self):
        if any(not (self.root/p).is_file() for p in ('venv/bin/python','model/config.json','model/model.safetensors','model/style_vectors.npy','bert/model.safetensors','bert/tokenizer_config.json')):
            raise RuntimeError('Koharune Ami is not installed. Run scripts/install_style_bert.py.')
        if any(not (self.dictionary/p).is_file() for p in ('sys.dic','char.bin','matrix.bin')):
            raise RuntimeError('The local Japanese dictionary is missing. Run scripts/install_voicevox.py.')

    async def _stop(self):
        process,self._process=self._process,None;self._ready=False
        if process is not None:
            if process.returncode is None:
                try:process.kill()
                except ProcessLookupError:pass
            await process.wait()

    async def _cleanup(self):
        task=asyncio.create_task(self._stop())
        while not task.done():
            try:await asyncio.shield(task)
            except asyncio.CancelledError:pass
        task.result()

    async def _launch(self):
        self.check_installation();await self._stop()
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'worker.log').open('ab') as log:
            start=asyncio.create_task(asyncio.create_subprocess_exec(str(self.root/'venv/bin/python'),'-u',str(ROOT/'style_bert_worker.py'),
                str(self.root),self.device,str(self.threads),str(self.dictionary),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                stderr=log,limit=12*1024*1024,env={**os.environ,'PYTHONUNBUFFERED':'1'}))
            try:self._process=await asyncio.shield(start)
            except asyncio.CancelledError:
                while not start.done():
                    try:await asyncio.shield(start)
                    except asyncio.CancelledError:pass
                self._process=start.result();raise
        ready=json.loads(await self._process.stdout.readline())
        if ready.get('ready') is not True:raise RuntimeError('Koharune Ami could not start')
        self._ready=True

    async def warmup(self):
        async with self._lock:
            if self.ready:return
            try:await asyncio.wait_for(self._launch(),self.load_timeout)
            except BaseException:await self._cleanup();raise

    async def _request(self,text,emotion):
        if not self.ready:raise RuntimeError('Koharune Ami is warming up')
        style,weight=style_for_emotion(emotion)
        self._process.stdin.write((json.dumps({'text':text,'style':style,'weight':weight},ensure_ascii=False)+'\n').encode())
        await self._process.stdin.drain()
        result=json.loads(await self._process.stdout.readline())
        data=base64.b64decode(result['wav'],validate=True)
        if not data or len(data)>8*1024*1024:raise ValueError('Invalid Koharune Ami audio')
        self.last_metrics={key:result.get(key) for key in ('seconds','duration','style')}
        logger.info('Koharune Ami synthesis: %s',self.last_metrics)
        return data

    async def synthesize(self,text,emotion='neutral'):
        if not isinstance(text,str) or not 1<=len(text)<=350 or not JAPANESE.search(text):raise ValueError('A short Japanese sentence is required')
        async with self._lock:
            try:return await asyncio.wait_for(self._request(text,emotion),self.timeout)
            except BaseException:await self._cleanup();raise

    async def close(self):
        async with self._lock:await self._stop()


class ExpressiveTTS:
    def __init__(self,config,*,primary=None,voicevox=None):
        self.primary=primary or StyleBertTTS(config);self.voicevox=voicevox or VoicevoxTTS(config)
        self.path=Path(config['tts'].get('selection_path',ROOT/'.chassie/tts-selection.json'))
        self.preferred='style_bert';self._warm_task=None;self._turn_provider=None;self._turn_failed=False;self._closed=False
        self.reason=None;self.active=None;self._warm_error=None
        if self.path.is_file():
            try:
                choice=json.loads(self.path.read_text()).get('engine')
                if choice in ('style_bert','voicevox'):self.preferred=choice
            except (OSError,ValueError,AttributeError):pass

    def check_installation(self):
        if self.preferred=='voicevox':self.voicevox.check_installation()

    def start(self):
        if self._closed or self.preferred!='style_bert' or self.primary.ready:return
        if self._warm_task is None or self._warm_task.done():self._warm_task=asyncio.create_task(self._warm())

    async def _warm(self):
        try:
            await self.primary.warmup();self._warm_error=None
        except asyncio.CancelledError:raise
        except Exception as exc:
            self._warm_error=type(exc).__name__
            logger.warning('Koharune Ami unavailable (%s)',type(exc).__name__)

    def begin_turn(self):
        self._turn_provider=self.preferred;self._turn_failed=False;self.active=None
        self.reason='selected' if self.preferred=='voicevox' else None
        self.start()

    async def synthesize(self,text,emotion='neutral'):
        if self._turn_provider is None:self.begin_turn()
        if self._turn_provider=='voicevox':
            data=await self.voicevox.synthesize(text,emotion);self.active='voicevox';return data
        if self._turn_failed:raise RuntimeError('Koharune Ami failed for this reply')
        try:
            if not self.primary.ready:
                self.reason='warming';self.start()
                if self._warm_task:await self._warm_task
                if not self.primary.ready:raise RuntimeError('Koharune Ami is unavailable')
            self.reason=None
            data=await self.primary.synthesize(text,emotion);self.active='style_bert';return data
        except asyncio.CancelledError:raise
        except Exception as exc:
            self._turn_failed=True;self.active=None
            self.reason='slow' if isinstance(exc,TimeoutError) else 'unavailable'
            self._warm_error=self.reason
            logger.warning('Koharune Ami speech failed: %s',self.reason)
            raise

    async def select(self,engine):
        if engine not in ('style_bert','voicevox'):raise ValueError('Unknown speech engine')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        pending=self.path.with_suffix('.tmp');pending.write_text(json.dumps({'engine':engine}));pending.replace(self.path)
        self.preferred=engine;self._turn_provider=None;self.reason=None;self.active=None
        if engine=='voicevox':
            await self._cancel_warm();await self.primary.close()
        else:self._warm_error=None;self._turn_failed=False;self.start()

    def status(self):
        warming=bool(self._warm_task and not self._warm_task.done())
        reason=self.reason
        if reason!='slow' and self._warm_error and not self.primary.ready and not warming and self.preferred=='style_bert':reason='unavailable'
        return {'selected':self.preferred,'active':self.active,'ready':bool(self.primary.ready),
                'warming':warming,'reason':reason}

    async def _cancel_warm(self):
        if self._warm_task:
            self._warm_task.cancel();await asyncio.gather(self._warm_task,return_exceptions=True);self._warm_task=None

    async def close(self):
        self._closed=True;await self._cancel_warm()
        await self.primary.close();await self.voicevox.close()
