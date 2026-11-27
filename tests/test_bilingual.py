import json
import pytest
from brain.bilingual import BilingualChunker, display_translation

PAIR={'emotion':'happy','ja':'こんにちは。','en':'Hello.'}

def test_pairs_survive_every_character_boundary():
    wire=json.dumps(PAIR,ensure_ascii=False)+'\n'+json.dumps({**PAIR,'emotion':'sad','en':'Sorry.','ja':'ごめんなさい。'},ensure_ascii=False)
    parser=BilingualChunker();items=[]
    for char in wire: items.extend(parser.feed(char))
    items.extend(parser.finish())
    assert items==[('happy','Hello.','こんにちは。'),('sad','Sorry.','ごめんなさい。')]

@pytest.mark.parametrize('value',[
    'Hello.', '{"en":"Hello."}', json.dumps({**PAIR,'ja':'Hello.'}),
    json.dumps({**PAIR,'en':'こんにちは。'}), json.dumps({**PAIR,'emotion':'invented'}),
    json.dumps({**PAIR,'en':'x'*701}), '```json\n'+json.dumps(PAIR)+'\n```',
])
def test_invalid_pairs_never_become_spoken_text(value):
    parser=BilingualChunker()
    with pytest.raises(ValueError):
        parser.feed(value);parser.finish()


def test_history_shows_only_valid_translations_not_partial_protocol():
    wire=json.dumps(PAIR,ensure_ascii=False)+'\n{"emotion":"sad","ja":"'
    assert display_translation(wire)=='[happy] Hello.'
    assert display_translation('{"emotion":')==''
    assert display_translation('[Response interrupted; only completed spoken sentences follow.] Hello.').endswith('Hello.')


def test_buffer_is_bounded_and_empty_response_fails():
    with pytest.raises(ValueError): BilingualChunker().feed('x'*5000)
    with pytest.raises(ValueError): BilingualChunker().finish()

from test_orchestrator import app, playback_fixture
import asyncio
from unittest.mock import Mock
from brain.hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG


@pytest.mark.asyncio
@pytest.mark.parametrize('user_text',['Halo, apa kabar?','Hello, how are you?'])
async def test_japanese_audio_english_subtitles_and_input_preserved(app,user_text):
    playback=playback_fixture(app);app._bilingual=True
    spoken=[]
    async def synthesize(text,*,emotion):
        import numpy as np
        spoken.append((text,emotion));yield np.ones(480)
    app._tts.synthesize_stream=synthesize
    async def stream(text,**kw):
        assert text==user_text
        for c in json.dumps(PAIR,ensure_ascii=False)+'\n': yield c
    app._hermes.stream_message=stream
    task=asyncio.create_task(app._run_turn({'text':user_text,'source':'text'}))
    try:
        await asyncio.wait_for(playback.first_draining.wait(),2)
        events=[c.args[0] for c in app._broadcast_to_ui.call_args_list]
        assert spoken==[('こんにちは。','happy')]
        assert any(e.get('type')=='subtitle' and e['text']=='Hello.' for e in events)
        assert app._stream_view['text']=='[happy] Hello.'
        assert any(e.get('type')=='chat_stream' and e['text']=='[happy] Hello.' for e in events)
        assert app._spoken==''
        playback.first_release.set();await asyncio.wait_for(task,2)
        assert app._spoken.strip()=='Hello.'
        assert app._stream_view['text']=='[happy] Hello.'
    finally:
        playback.first_release.set();task.cancel();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_invalid_translation_is_not_displayed_or_synthesized(app):
    playback_fixture(app);app._bilingual=True
    async def stream(*a,**kw): yield '{"ja":"こんにちは。","en":"Hello."}'
    app._hermes.stream_message=stream
    await app._run_turn({'text':'hi','source':'text'})
    assert app._stream_view['text']==''
    assert app._stream_view['interrupted']
    app._hermes.complete_response.assert_not_called()
    assert any('English translations' in c.args[0].get('text','') for c in app._broadcast_to_ui.call_args_list)


def test_bilingual_bridge_keeps_raw_pairs_internal_and_projects_english():
    bridge=HermesBridge({**CONFIG,'tts':{**CONFIG['tts'],'engine':'voicevox'}})
    raw=json.dumps(PAIR,ensure_ascii=False)
    bridge._messages.extend([{'role':'user','content':'Halo'},{'role':'assistant','content':raw}])
    assert bridge.get_history()[-1]['content']=='[happy] Hello.'
    assert bridge._messages[-1]['content']==raw
    assert 'newline-delimited JSON' in bridge._messages[0]['content']


def test_reconnect_during_partial_pair_does_not_duplicate_user(app):
    app._hermes.get_history.return_value=[{'role':'user','content':'Hi'},{'role':'assistant','content':''}]
    app._stream_view={'id':'test','user_text':'Hi','text':'','done':False}
    assert app._history_snapshot()['items']==[{'role':'user','text':'Hi'}]

@pytest.mark.asyncio
async def test_each_sentence_updates_voice_emotion_with_avatar(app):
    playback=playback_fixture(app);app._bilingual=True
    speech=[]
    async def synthesize(text,*,emotion):
        import numpy as np
        speech.append((text,emotion));yield np.ones(480)
    app._tts.synthesize_stream=synthesize
    async def stream(*a,**kw):
        yield json.dumps(PAIR,ensure_ascii=False)+'\n'
        yield json.dumps({'emotion':'thinking','ja':'少し考えましょう。','en':'Let us think.'},ensure_ascii=False)+'\n'
    app._hermes.stream_message=stream
    playback.first_release.set()
    await app._run_turn({'text':'hello','source':'text'})
    assert speech==[('こんにちは。','happy'),('少し考えましょう。','thinking')]
    assert [call.kwargs['emotion'] for call in app._audio_player.enqueue.call_args_list]==['happy','thinking']
    speech.clear()
    async def next_reply(*a,**kw):
        yield json.dumps({'emotion':'sad','ja':'残念ですね。','en':'That is a shame.'},ensure_ascii=False)
    app._hermes.stream_message=next_reply
    await app._run_turn({'text':'another reply','source':'text'})
    assert speech==[('残念ですね。','sad')]


def test_indonesian_translation_protocol_and_mixed_history():
    from brain.bilingual import bilingual_prompt
    assert '"id":"Halo!' in bilingual_prompt('id') and 'Indonesian translation' in bilingual_prompt('id')
    with pytest.raises(ValueError): bilingual_prompt('fr')
    pair = '{"emotion":"happy","ja":"こんにちは！","id":"Halo!"}\n'
    assert BilingualChunker('id').feed(pair) == [('happy', 'Halo!', 'こんにちは！')]
    with pytest.raises(ValueError): BilingualChunker('en').feed(pair)
    history = '{"emotion":"happy","ja":"はい","en":"Yes"}\n' + pair
    assert display_translation(history) == '[happy] Yes [happy] Halo!'


@pytest.mark.asyncio
async def test_translation_language_switch_persists_and_reaches_hermes(app, tmp_path):
    from brain.orchestrator import Orchestrator
    await app.handle_control({'type': 'set_translation_language', 'language': 'id'})
    assert app._settings()['translation_language'] == 'id'
    assert app._hermes.translation_language == 'id'
    with pytest.raises(ValueError): await app.handle_control({'type': 'set_translation_language', 'language': 'fr'})
    assert json.loads(app._speech_settings_path.read_text()) == {'translation_language': 'id', 'initiative_mode': 'normal'}


def test_hermes_prompt_follows_translation_language():
    bridge = HermesBridge({**CONFIG, 'tts': {**CONFIG['tts'], 'engine': 'voicevox'}})
    bridge.clear_history()
    bridge.translation_language = 'id'
    assert 'Indonesian translation' in bridge._messages[0]['content']
    with pytest.raises(ValueError): bridge.translation_language = 'fr'


def _vision(**enrollment):
    status={'camera':{'enabled':True,'available':True,'error':None},'screen':{'enabled':False,'available':False,'error':None},
            'identity':{'face_count':1,'matches':[],'error':None,'ready':True}}
    return Mock(enrollment=Mock(**enrollment),status=Mock(return_value=status),
                request_context=Mock(return_value=([],status)),camera_enabled=True)


def _action_stream(*lines):
    async def stream(*a, **kw):
        for line in lines: yield json.dumps(line, ensure_ascii=False) + '\n'
    return stream


@pytest.mark.asyncio
async def test_model_face_action_runs_before_speech(app):
    playback=playback_fixture(app);app._bilingual=True;playback.first_release.set()
    spoken=[]
    async def synthesize(text,*,emotion):
        import numpy as np
        spoken.append(text);yield np.ones(480)
    app._tts.synthesize_stream=synthesize
    app._vision=_vision(return_value=[.1]*512)
    app._hermes.stream_message=_action_stream({'action':'remember_face','name':'Artdi'},PAIR)
    await app._run_turn({'text':'bisa simpan muka gue? namaku Artdi','source':'text'})
    assert [p.name for p in app._memory.list_profiles() if app._memory.list_faces()]==['Artdi']
    assert spoken==['こんにちは。']
    assert any('Face remembered locally as Artdi' in c.args[0].get('text','') for c in app._broadcast_to_ui.call_args_list)


@pytest.mark.asyncio
async def test_failed_model_action_stops_reply_with_real_reason(app):
    playback=playback_fixture(app);app._bilingual=True;playback.first_release.set()
    app._tts.synthesize_stream=Mock(side_effect=AssertionError('must not speak'))
    app._vision=_vision(side_effect=ValueError('Face not saved. Face the camera alone in good light, then repeat your request.'))
    app._hermes.stream_message=_action_stream({'action':'remember_face','name':'Artdi'},PAIR)
    await app._run_turn({'text':'save my face please, I am Artdi','source':'text'})
    assert app._memory.list_faces()==[]
    assert app._stream_view['interrupted']
    assert any('Face the camera alone' in c.args[0].get('text','') for c in app._broadcast_to_ui.call_args_list)


@pytest.mark.asyncio
async def test_model_face_action_without_face_request_is_ignored(app):
    playback=playback_fixture(app);app._bilingual=True;playback.first_release.set()
    app._vision=_vision(return_value=[.1]*512)
    app._hermes.stream_message=_action_stream({'action':'remember_face','name':'Stranger'},PAIR)
    await app._run_turn({'text':'what is the weather like?','source':'text'})
    assert app._memory.list_faces()==[]
    app._vision.enrollment.assert_not_called()


@pytest.mark.asyncio
async def test_first_sentence_is_spoken_whole_with_one_subtitle(app):
    playback=playback_fixture(app);app._bilingual=True;playback.first_release.set()
    spoken=[]
    async def synthesize(text,*,emotion):
        import numpy as np
        spoken.append(text);yield np.ones(480)
    app._tts.synthesize_stream=synthesize
    pair={'emotion':'happy','ja':'お疲れ様、コーディングで疲れたんだね。ちょっと休んでいいんだよ。','en':'Good work. Take a break.'}
    app._hermes.stream_message=_action_stream(pair,PAIR)
    await app._run_turn({'text':'capek','source':'text'})
    assert spoken==['お疲れ様、コーディングで疲れたんだね。ちょっと休んでいいんだよ。','こんにちは。']  # One take: no break in her intonation.
    events=[c.args[0] for c in app._broadcast_to_ui.call_args_list]
    assert [e['text'] for e in events if e.get('type')=='subtitle' and e['text']]==['Good work. Take a break.','Hello.']
    assert [e['text'] for e in events if e.get('type')=='subtitle'][-1]=='' and sum(1 for e in events if e.get('type')=='subtitle' and not e['text'])<=2  # Cleared at the end, not between sentences.
    assert app._stream_view['text']=='[happy] Good work. Take a break. [happy] Hello.'
    assert app._spoken.split()==['Good','work.','Take','a','break.','Hello.']


def test_tolerant_chunker_skips_a_broken_line_but_not_an_empty_reply():
    good = '{"emotion":"happy","en":"Hello!","ja":"こんにちは！"}\n'
    chunker = BilingualChunker('en', tolerant=True)
    assert chunker.feed('{"emotion":"happy","ja":"こんにちは"\n' + good) == [('happy', 'Hello!', 'こんにちは！')]
    assert chunker.finish() == [] and chunker.dropped == 1
    with pytest.raises(ValueError):
        empty = BilingualChunker('en', tolerant=True); empty.feed('{"broken": \n'); empty.finish()


@pytest.mark.asyncio
async def test_one_broken_line_no_longer_fails_the_whole_reply(app):
    from test_orchestrator import playback_fixture
    playback_fixture(app).first_release.set()
    app._bilingual = True
    spoken = []
    async def synthesize(text, *, emotion):
        spoken.append(text); yield np.ones(480)
    app._tts.synthesize_stream = synthesize
    async def stream(*a, **kw):
        yield '{"emotion":"happy","ja":"壊れた"\n{"emotion":"happy","ja":"大丈夫だよ。","en":"It is fine."}\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'halo', 'source': 'text'})
    assert spoken == ['大丈夫だよ。']
    assert not any('did not contain valid' in str(c.args[0].get('text', '')) for c in app._broadcast_to_ui.call_args_list)
