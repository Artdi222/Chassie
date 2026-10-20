import asyncio
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from hermes_bridge import HermesBridge
from tts_engine import TTSEngine, sentence_chunks

CONFIG={'hermes':{'gateway_url':'http://localhost:8642','endpoint':'/v1/chat/completions',
 'health_endpoint':'/health','timeout':1,'model':'test','system_prompt':'Use English.'},
 'tts':{'sample_rate':24000}}

@pytest.mark.asyncio
async def test_local_gateway_key_file_and_environment_override(tmp_path,monkeypatch):
    keyfile=tmp_path/'api-key'
    keyfile.write_text('synthetic-local-key-only\n')
    config={**CONFIG,'hermes':{**CONFIG['hermes'],'api_key_file':str(keyfile),'api_key_env':'CHASSIE_HERMES_API_KEY'}}
    monkeypatch.delenv('CHASSIE_HERMES_API_KEY',raising=False)
    h=HermesBridge(config)
    await h.connect()
    try: assert h._session.headers['Authorization']=='Bearer synthetic-local-key-only'
    finally: await h.close()
    monkeypatch.setenv('CHASSIE_HERMES_API_KEY','synthetic-environment-key')
    h=HermesBridge(config)
    await h.connect()
    try: assert h._session.headers['Authorization']=='Bearer synthetic-environment-key'
    finally: await h.close()

class Response:
    status=200
    def __init__(self,gate,payload): self.gate=gate; self.payload=payload
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def json(self): await self.gate.wait(); return self.payload
class Session:
    def __init__(self,r): self.r=r
    def post(self,*a,**kw): return self.r

@pytest.mark.asyncio
async def test_batch_context_shares_user_message_and_stays_out_of_history():
    h=HermesBridge(CONFIG);gate=asyncio.Event();gate.set()
    response=Response(gate,{'choices':[{'message':{'content':'Hello.'}}]})
    captured=[]
    class CaptureSession:
        def post(self,*args,**kwargs):
            captured.append(kwargs['json'])
            return response
    h._session=CaptureSession()
    await h.send_message('hello',context='local observations')
    users=[m for m in captured[0]['messages'] if m['role']=='user']
    assert len(users)==1 and users[0]['content'].startswith('hello\n\nContext data')
    assert h.get_history()[-2]['content']=='hello'

@pytest.mark.asyncio
async def test_clear_invalidates_response_without_repopulating_history():
    h=HermesBridge(CONFIG); gate=asyncio.Event()
    h._session=Session(Response(gate,{'choices':[{'message':{'content':'[happy] Old answer'}}]}))
    task=asyncio.create_task(h.send_message('private question'))
    await asyncio.sleep(0)
    h.clear_history(); gate.set()
    with pytest.raises(asyncio.CancelledError): await task
    assert len(h.get_history())==1

@pytest.mark.asyncio
async def test_bad_content_is_reported_not_added_to_history():
    h=HermesBridge(CONFIG); gate=asyncio.Event();gate.set()
    h._session=Session(Response(gate,{'choices':[{'message':{'content':None}}]}))
    with pytest.raises(RuntimeError): await h.send_message('hello')
    assert len(h.get_history())==1

@pytest.mark.asyncio
@pytest.mark.parametrize(('content','notice'),[
    ('API call failed after 3 retries: HTTP 429: synthetic exhausted quota','quota'),
    ('API call failed after 3 retries: HTTP 401: synthetic invalid credential','authentication'),
    ('API call failed after 3 retries: HTTP 503: synthetic unavailable provider','provider'),
])
async def test_gateway_wrapped_provider_failure_is_not_a_spoken_reply(content,notice):
    h=HermesBridge(CONFIG);gate=asyncio.Event();gate.set()
    h._session=Session(Response(gate,{'choices':[{'message':{'content':content}}]}))
    with pytest.raises(RuntimeError,match=notice): await h.send_message('synthetic test')
    assert len(h.get_history())==1
    assert h._pending is None

@pytest.mark.asyncio
async def test_explaining_an_error_is_still_a_valid_reply():
    h=HermesBridge(CONFIG);gate=asyncio.Event();gate.set()
    content='[concerned] The message API call failed after 3 retries means the provider could not answer.'
    h._session=Session(Response(gate,{'choices':[{'message':{'content':content}}]}))
    assert await h.send_message('Explain this error')==content

def test_sentence_chunks_keep_decimals_and_abbreviations_and_emotion_owned_externally():
    assert sentence_chunks('Dr. Smith paid 3.14 dollars. Next sentence!')==['Dr. Smith paid 3.14 dollars.','Next sentence!']
    assert sentence_chunks('   ')==[]

@pytest.mark.asyncio
async def test_tts_decodes_from_memory_resamples_and_reports_empty(monkeypatch):
    samples=(np.sin(np.arange(1600)/10)*10000).astype('<i2')
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(samples.tobytes())
    data=buf.getvalue()
    def ready(engine,audio):
        engine._voicevox.check_installation=lambda:None
        engine._voicevox.synthesize=AsyncMock(return_value=audio)
        engine.load_model();return engine
    t=ready(TTSEngine(CONFIG),data)
    chunks=[c async for c in t.synthesize_stream('test')]
    assert chunks[0].dtype==np.float32 and chunks[0].ndim==1
    assert 2300<=len(chunks[0])<=2500
    limited=ready(TTSEngine({**CONFIG,'tts':{**CONFIG['tts'],'max_audio_seconds':0.05}}),data)
    with pytest.raises(RuntimeError,match='Speech synthesis failed'):
        _=[c async for c in limited.synthesize_stream('oversized decoded audio')]
    t._voicevox.synthesize=AsyncMock(return_value=b'')
    with pytest.raises(RuntimeError):
        _=[c async for c in t.synthesize_stream('test')]
