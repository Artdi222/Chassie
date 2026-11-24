import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from companion import MemoryStore
from companion.vault import VaultMemory
from stt_engine import SpeechEvent
from voice_identity import VoiceIdentity, match_voice
from test_orchestrator import app


def test_vault_uses_hermes_notes_and_rejects_handwritten_mutations(tmp_path):
    home=tmp_path/'hermes';plugin=home/'plugins/chassie';plugin.mkdir(parents=True)
    source=Path.home()/'.hermes/plugins/chassie/store.py'
    if not source.exists():pytest.skip('Chassie memory plugin is not installed')
    shutil.copyfile(source,plugin/'store.py')
    vault=tmp_path/'Memory';vault.mkdir();(vault/'handwritten.md').write_text('A handwritten note about my workspace.')
    (home/'chassie.json').write_text(json.dumps({'vault_path':str(vault)}))
    store=VaultMemory(home)
    assert store.status()['available']
    manual=next(row for row in store.list() if row['source']=='handwritten.md')
    assert manual['editable'] is False
    with pytest.raises(ValueError):store.delete(manual['id'])
    saved=store.add('I prefer concise and clear explanations.')
    managed=next(row for row in store.list() if row['editable'])
    # Saved as a readable note in its taxonomy folder, listed in the generated overview.
    assert managed['source']==saved['source_file'] and managed['source'].startswith('_generated/chassie/People/')
    note=(vault/managed['source']).read_text()
    assert note.startswith('---\nid: '+saved['id']) and '\n# ' in note and '[[Artdi]]' in note
    assert managed['content']=='I prefer concise and clear explanations.'
    assert Path(managed['source']).stem in (vault/'_generated/chassie/Memories.md').read_text()
    updated=store.update(managed['id'],'I prefer short explanations in Indonesian.')
    assert len([r for r in store.list() if r['editable']])==1
    store.delete(updated['id'])
    assert not any(r['editable'] for r in store.list())
    assert '[[' not in (vault/'_generated/chassie/Memories.md').read_text()
    assert (vault/'handwritten.md').is_file()


def test_voice_consent_quality_matching_and_cancellation(tmp_path):
    with MemoryStore(tmp_path/'memory.sqlite') as store:
        person=store.create_profile('Synthetic owner',consent=True)
        feature=np.zeros(256,dtype=np.float32);feature[0]=1
        engine=VoiceIdentity(store,extractor=Mock(),clock=lambda:10)
        engine._embedding=Mock(return_value=feature)
        with pytest.raises(ValueError):engine.enroll(person.id,consent=False)
        with pytest.raises(ValueError):store.save_voice(person.id,feature.tolist(),consent=False)
        engine.enroll(person.id,consent=True)
        assert 'enrollment' in engine.process(np.zeros(64000,dtype=np.float32),16000)
        assert not store.list_voices()
        audio=np.full(64000,.1,dtype=np.float32)
        result=engine.process(audio,16000)
        assert result['saved'] and not engine.enrolling
        assert engine.process(audio,16000)['match']['profile_id']==person.id
        assert engine.process(audio[:8000],16000)=={'match':None}
        assert engine.last['match'] is None
        engine.enroll(person.id,consent=True)
        def cancel_during_compute(*args):engine.cancel();return feature
        engine._embedding=cancel_during_compute
        revision=store.revision
        assert engine.process(audio,16000) is None
        assert store.revision==revision
        unknown=np.zeros(256);unknown[1]=1
        assert match_voice(unknown,store.list_voices()) is None
        assert match_voice(feature,store.list_voices()*2) is None
        store.delete_voice(person.id)
        assert not store.list_voices()
        assert not list(tmp_path.glob('*.wav'))


@pytest.mark.asyncio
async def test_introduction_requires_consent_and_never_selects_new_owner(app):
    app._broadcast_to_ui=AsyncMock();app._automatic_memory=True
    owner=app._memory.create_profile('Owner',consent=True);app._session_context.set_owner(owner.id)
    app._vision=Mock(enrollment=Mock(return_value=[.1]*512))
    with pytest.raises(ValueError):await app.handle_control({'type':'enroll_person','name':'Friend','face':True,'consent':False})
    assert len(app._memory.list_profiles())==1
    await app.handle_control({'type':'enroll_person','name':'Friend','face':True,'consent':True})
    assert app._session_context.owner_profile_id==owner.id
    settings=app._settings();person=settings['people'][0]
    assert person['name']=='Friend' and person['face'] and not person['voice']
    assert 'embedding' not in json.dumps(settings['people'])
    app._memory.add_memory(owner.id,'My original text memory',source='user',consent=True)
    await app.handle_control({'type':'forget_person','person_id':person['id']})
    assert not app._settings()['people']
    assert len(app._memory.list_memories(owner.id))==1


@pytest.mark.asyncio
async def test_enrollment_speech_is_never_sent_as_chat_and_other_voice_pauses_memory(app):
    app._broadcast_to_ui=AsyncMock();app._automatic_memory=True;app._input_mode='hands_free';app._guest_privacy=True
    owner=app._memory.create_profile('Owner',consent=True);app._session_context.set_owner(owner.id)
    await app._handle_speech_event(SpeechEvent('transcript',0,0,4,'My voice sample',{'enrollment':'Saved','saved':True}))
    assert app._ui_input_queue.empty()
    await app._handle_speech_event(SpeechEvent('transcript',0,0,4,'I like coffee',{'match':{'profile_id':'other','name':'Friend'}}))
    assert json.loads(app._context_text())['scope']=='shared'
    assert 'profile_id' not in json.loads(app._context_text())
    assert (await app._ui_input_queue.get())['text']=='I like coffee'


@pytest.mark.asyncio
async def test_auto_presence_requires_stable_owner_and_cannot_unlock_voice_scope(app):
    app._automatic_memory=True;app._broadcast_to_ui=AsyncMock();app._guest_privacy=True
    owner=app._memory.create_profile('Owner',consent=True);app._session_context.set_owner(owner.id)
    def status(matches,count=1):return {'camera':{'enabled':True,'available':True},'identity':{'face_count':count,'ready':True,'presence_ready':True,'matches':matches}}
    await app._update_presence(status([],2),10)
    assert json.loads(app._context_text())['scope']=='shared'
    await app._update_presence(status([{'profile_id':'someone-else'}]),11)
    assert json.loads(app._context_text())['scope']=='shared'
    single=status([{'profile_id':owner.id}])
    await app._update_presence(single,12);await app._update_presence(single,16.9)
    assert json.loads(app._context_text())['scope']=='shared'
    await app._update_presence(status([]),17)  # Unknown resets the dwell.
    await app._update_presence(single,18);await app._update_presence(single,23)
    assert json.loads(app._context_text())['scope']=='personal'
    await app._pause_personal('voice-presence','Unknown voice')
    await app._update_presence(single,24);await app._update_presence(single,40)
    assert json.loads(app._context_text())['scope']=='shared'


@pytest.mark.asyncio
async def test_automatic_memory_controls_use_vault_and_retain_scope(app):
    app._automatic_memory=True;app._broadcast_to_ui=AsyncMock()
    owner=app._memory.create_profile('Owner',consent=True);app._session_context.set_owner(owner.id)
    app._vault=Mock(list=Mock(return_value=[{'id':'vault-note','content':'A vault memory'}]))
    assert (await app.handle_control({'type':'list_memories'}))['items'][0]['id']=='vault-note'
    await app.handle_control({'type':'add_memory','content':'I prefer concise responses','consent':True})
    app._vault.add.assert_called_once_with('I prefer concise responses')
    assert not app._memory.list_memories(owner.id)
    app._session_context.mark_guest_present('other','Friend')
    with pytest.raises(ValueError):await app.handle_control({'type':'list_memories'})
    with pytest.raises(ValueError):await app.handle_control({'type':'add_memory','content':'I prefer coffee','consent':True})
    assert app._vault.add.call_count==1


@pytest.mark.asyncio
async def test_listening_reaction_tracks_speech_without_interrupting_reply(app):
    app._broadcast_to_ui=AsyncMock()
    await app._handle_speech_event(SpeechEvent('speech_start',0,0,0))
    assert app._current_status=='listening'
    await app._handle_speech_event(SpeechEvent('transcript',0,0,4,'hello'))
    assert app._current_status=='idle'
    app._current_status='thinking'
    await app._handle_speech_event(SpeechEvent('speech_start',0,0,0))
    assert app._current_status=='thinking'


def test_startup_uses_only_the_configured_owner_without_manual_profile_selection(app):
    from orchestrator import Orchestrator
    owner=app._memory.create_profile('Configured owner',consent=True)
    config={**app._config,'companion':{**app._config['companion'],'automatic_memory':True},
            'hermes':{'personal_memory_profile_id':owner.id}}
    parts={'stt':app._stt,'hermes':app._hermes,'player':app._audio_player,
           'tts':app._tts,'analyzer':app._audio_analyzer,'vault':Mock(),'speaker':VoiceIdentity(app._memory)}
    restarted=Orchestrator(config,components=parts)
    try:
        assert restarted._session_context.owner_profile_id==owner.id
        assert json.loads(restarted._context_text())['scope']=='personal'
        assert restarted._stt.speaker_identity is parts['speaker']
    finally:restarted._memory.close()
    config['hermes']['personal_memory_profile_id']='missing-owner'
    missing=Orchestrator(config,components=parts)
    try:assert missing._session_context.owner_profile_id is None
    finally:missing._memory.close()


@pytest.mark.asyncio
async def test_default_keeps_personal_scope_when_others_appear_and_tells_the_model(app):
    from types import SimpleNamespace
    app._automatic_memory=True;app._broadcast_to_ui=AsyncMock();app._input_mode='hands_free'
    owner=app._memory.create_profile('Owner',consent=True);app._session_context.set_owner(owner.id)
    assert app._guest_privacy is False
    status={'camera':{'enabled':True,'available':True},'identity':{'face_count':2,'ready':True,'presence_ready':True,
            'matches':[{'profile_id':owner.id,'name':'Owner'},{'profile_id':'f','name':'Friend'}]}}
    await app._update_presence(status,10)
    await app._handle_speech_event(SpeechEvent('transcript',0,0,4,'halo semua',{'match':{'profile_id':'f','name':'Friend'}}))
    app._vision=SimpleNamespace(camera_enabled=True,screen_enabled=False,status=lambda:status)
    context=json.loads(app._context_text())
    assert context['scope']=='personal'
    assert context['others_in_view']['count']==1 and context['others_in_view']['recognized']==['Friend']
