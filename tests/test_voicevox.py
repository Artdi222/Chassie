import asyncio
from unittest.mock import AsyncMock, Mock
import pytest
from voicevox_tts import VoicevoxTTS
from emotion_parser import VALID_EMOTIONS

CONFIG={'tts':{'engine':'voicevox','sample_rate':24000,'timeout':0.02}}

@pytest.mark.asyncio
async def test_cancellation_kills_and_reaps_owned_inference(monkeypatch):
    t=VoicevoxTTS(CONFIG);entered=asyncio.Event()
    process=Mock(returncode=None,wait=AsyncMock())
    async def request(*a):
        t._process=process;entered.set();await asyncio.Event().wait()
    monkeypatch.setattr(t,'_request',request)
    task=asyncio.create_task(t.synthesize('こんにちは。'))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    process.kill.assert_called_once();process.wait.assert_awaited_once()
    assert t._process is None
    monkeypatch.setattr(t,'_request',AsyncMock(return_value=b'next-audio'))
    assert await t.synthesize('次の返事です。')==b'next-audio'

@pytest.mark.asyncio
async def test_timeout_cleans_up_and_english_is_rejected(monkeypatch):
    t=VoicevoxTTS(CONFIG)
    process=Mock(returncode=None,wait=AsyncMock())
    async def request(*a):
        t._process=process;await asyncio.Event().wait()
    monkeypatch.setattr(t,'_request',request)
    with pytest.raises(asyncio.TimeoutError): await t.synthesize('こんにちは。')
    assert t._process is None
    process.kill.assert_called_once()
    with pytest.raises(RuntimeError,match='Japanese'): await t.synthesize('Hello.')

@pytest.mark.asyncio
async def test_close_reaps_warm_process():
    t=VoicevoxTTS(CONFIG);p=Mock(returncode=None,wait=AsyncMock());t._process=p
    await t.close();await t.close()
    p.kill.assert_called_once();p.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_every_mood_sends_normal_style_to_worker():
    import json
    t=VoicevoxTTS(CONFIG)
    process=Mock(returncode=None)
    process.stdin.drain=AsyncMock()
    process.stdout.readline=AsyncMock(return_value=b'{"wav":"YXVkaW8="}\n')
    t._process=process
    for emotion in sorted(VALID_EMOTIONS):
        assert await t._request('こんにちは。',emotion)==b'audio'
        request=json.loads(process.stdin.write.call_args.args[0])
        assert request['style']==20, emotion
        assert request['speed']==1.0

@pytest.mark.asyncio
async def test_repeated_stop_during_process_creation_cannot_orphan_worker(monkeypatch):
    t=VoicevoxTTS(CONFIG);entered=asyncio.Event();release=asyncio.Event()
    process=Mock(returncode=None,wait=AsyncMock())
    async def create(*a,**kw):
        entered.set();await release.wait();return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',create)
    task=asyncio.create_task(t.synthesize('こんにちは。'))
    await entered.wait();task.cancel();await asyncio.sleep(0)
    task.cancel();await asyncio.sleep(0);release.set()
    with pytest.raises(asyncio.CancelledError): await task
    assert t._process is None
    process.kill.assert_called_once();process.wait.assert_awaited_once()
