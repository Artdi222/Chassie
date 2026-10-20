import asyncio
from unittest.mock import AsyncMock,Mock
import pytest
from style_bert_tts import ExpressiveTTS, style_for_emotion


def make(tmp_path,ready=True):
    config={'tts':{'engine':'style_bert','sample_rate':24000,'selection_path':str(tmp_path/'tts.json'),'style_bert_timeout':.02}}
    primary=Mock(ready=ready,warmup=AsyncMock(),synthesize=AsyncMock(return_value=b'ami'),close=AsyncMock())
    voicevox=Mock(synthesize=AsyncMock(return_value=b'voicevox'),check_installation=Mock(),close=AsyncMock())
    return ExpressiveTTS(config,primary=primary,voicevox=voicevox),primary,voicevox


def test_styles_only_use_real_ami_presets():
    assert style_for_emotion('happy')==('るんるん',.8)
    assert style_for_emotion('sleepy')[0]=='よふかし'
    assert style_for_emotion('shy')[0]=='ささやきB（有声）'
    assert style_for_emotion('angry')[0]=='Neutral'


@pytest.mark.asyncio
async def test_each_sentence_receives_its_own_mood(tmp_path):
    engine,primary,voicevox=make(tmp_path);engine.begin_turn()
    assert await engine.synthesize('こんにちは。','happy')==b'ami'
    assert await engine.synthesize('大丈夫ですか。','concerned')==b'ami'
    assert [call.args[1] for call in primary.synthesize.await_args_list]==['happy','concerned']
    voicevox.synthesize.assert_not_awaited()
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('error',[TimeoutError(),RuntimeError('failed')])
async def test_failure_never_switches_to_voicevox(tmp_path,error):
    engine,primary,voicevox=make(tmp_path);primary.synthesize.side_effect=error
    engine.begin_turn()
    with pytest.raises(type(error)):await engine.synthesize('こんにちは。','happy')
    primary.ready=False
    with pytest.raises(RuntimeError):await engine.synthesize('次の文です。','sad')
    voicevox.synthesize.assert_not_awaited()
    assert primary.synthesize.await_count==1
    assert engine.status()['selected']=='style_bert'
    assert engine.status()['active'] is None
    assert engine.status()['reason']==('slow' if isinstance(error,TimeoutError) else 'unavailable')
    primary.ready=True;primary.synthesize.side_effect=None
    engine.begin_turn()
    assert await engine.synthesize('もう一度。')==b'ami'
    await engine.close()


@pytest.mark.asyncio
async def test_stop_never_generates_voicevox(tmp_path):
    engine,primary,voicevox=make(tmp_path);primary.synthesize.side_effect=asyncio.CancelledError()
    engine.begin_turn()
    with pytest.raises(asyncio.CancelledError):await engine.synthesize('こんにちは。')
    voicevox.synthesize.assert_not_awaited()
    await engine.close()


@pytest.mark.asyncio
async def test_warming_waits_for_selected_ami(tmp_path):
    engine,primary,voicevox=make(tmp_path,ready=False)
    entered=asyncio.Event();release=asyncio.Event()
    async def warm():
        entered.set();await release.wait();primary.ready=True
    primary.warmup.side_effect=warm
    engine.begin_turn()
    task=asyncio.create_task(engine.synthesize('こんにちは。'))
    await entered.wait();await asyncio.sleep(0)
    assert not task.done()
    voicevox.synthesize.assert_not_awaited()
    release.set()
    assert await task==b'ami'
    assert engine.status()['active']=='style_bert'
    await engine.close()


@pytest.mark.asyncio
async def test_cancel_during_warmup_never_speaks(tmp_path):
    engine,primary,voicevox=make(tmp_path,ready=False)
    entered=asyncio.Event()
    async def warm():entered.set();await asyncio.Event().wait()
    primary.warmup.side_effect=warm
    task=asyncio.create_task(engine.synthesize('こんにちは。'))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert engine._warm_task.cancelled()
    primary.synthesize.assert_not_awaited();voicevox.synthesize.assert_not_awaited()
    await engine.close()


@pytest.mark.asyncio
async def test_manual_voicevox_selection_survives_restart(tmp_path):
    engine,primary,voicevox=make(tmp_path)
    await engine.select('voicevox');engine.begin_turn()
    assert await engine.synthesize('こんにちは。')==b'voicevox'
    restarted,_,_=make(tmp_path)
    assert restarted.preferred=='voicevox'
    with pytest.raises(ValueError):await engine.select('unknown')
    assert restarted.preferred=='voicevox'
    await engine.close();await restarted.close()


@pytest.mark.asyncio
async def test_worker_timeout_kills_and_reaps_process(tmp_path,monkeypatch):
    from style_bert_tts import StyleBertTTS
    engine=StyleBertTTS({'tts':{'sample_rate':24000,'style_bert_timeout':.1}})
    process=Mock(returncode=None,wait=AsyncMock())
    async def request(*args):engine._process=process;await asyncio.Event().wait()
    monkeypatch.setattr(engine,'_request',request)
    with pytest.raises(TimeoutError):await engine.synthesize('こんにちは。')
    assert engine._process is None and not engine.ready
    process.kill.assert_called_once();process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_stop_during_spawn_does_not_orphan_worker(tmp_path,monkeypatch):
    from style_bert_tts import StyleBertTTS
    engine=StyleBertTTS({'tts':{'sample_rate':24000,'style_bert_dir':str(tmp_path)}})
    engine.check_installation=Mock();entered=asyncio.Event();release=asyncio.Event()
    process=Mock(returncode=None,wait=AsyncMock())
    async def create(*args,**kwargs):entered.set();await release.wait();return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',create)
    task=asyncio.create_task(engine.warmup());await entered.wait()
    task.cancel();await asyncio.sleep(0);task.cancel();await asyncio.sleep(0);release.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert engine._process is None
    process.kill.assert_called_once();process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_warmup_is_visible_before_first_chat(tmp_path):
    engine,primary,voicevox=make(tmp_path,ready=False)
    primary.warmup.side_effect=RuntimeError('Synthetic startup failure')
    engine.start();await engine._warm_task
    assert engine.status()['reason']=='unavailable'
    assert not engine.status()['warming']
    with pytest.raises(RuntimeError):await engine.synthesize('こんにちは。')
    voicevox.synthesize.assert_not_awaited()
    await engine.close()


def test_style_bert_uses_japanese_english_protocol():
    from hermes_bridge import HermesBridge
    from test_hermes_tts import CONFIG
    bridge=HermesBridge({**CONFIG,'tts':{**CONFIG['tts'],'engine':'style_bert'}})
    assert bridge._bilingual
    assert 'Japanese' in bridge._system_prompt and 'translation' in bridge._system_prompt
