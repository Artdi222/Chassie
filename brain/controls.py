"""UI control commands and the settings snapshot broadcast to every client."""
from __future__ import annotations
import asyncio
import os
from dataclasses import asdict
import json
import logging
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4
from memory.store import bounded_text
from speech.tts_engine import TTSEngine
from brain.bilingual import LANGUAGES
from brain.config import ROOT, save_local
from brain import updates
from speech import voices

logger=logging.getLogger('orchestrator')


BRAIN_KEYS=('provider','text_model','vision_model','background_model')
# Key variable Hermes reads for each provider (hermes_cli.providers, checked 2026-11-27). Others: set up in Hermes.
PROVIDER_KEYS={'anthropic':'ANTHROPIC_API_KEY','openrouter':'OPENROUTER_API_KEY','deepseek':'DEEPSEEK_API_KEY',
               'gemini':'GOOGLE_API_KEY','xai':'XAI_API_KEY','groq':'GROQ_API_KEY','mistral':'MISTRAL_API_KEY'}


def env_names(path):
    try: return {line.split('=',1)[0].strip() for line in Path(path).read_text(encoding='utf-8').splitlines() if '=' in line and line.split('=',1)[1].strip()}
    except OSError: return set()


def write_env(path,name,value):
    """Set one NAME=value line in Hermes's .env (private file); other lines stay."""
    path=Path(path)
    lines=path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    lines=[line for line in lines if line.split('=',1)[0].strip()!=name]+[f'{name}={value}']
    pending=path.with_suffix('.tmp')
    pending.touch(mode=0o600);pending.chmod(0o600)
    pending.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    pending.replace(path)


AVATAR_WINDOW_ACTIONS=('smaller','larger','zoom_out','zoom_in','frame_up','frame_down','reset','click_through')

class ControlsMixin:
    def _settings(self):
        faces={p['profile_id'] for p in self._memory.list_faces()}
        voices={p['profile_id'] for p in self._memory.list_voices()}
        return {'type':'settings','automatic_memory':self._automatic_memory,
                'people':[{'id':p.id,'name':p.name,'face':p.id in faces,'voice':p.id in voices}
                          for p in self._memory.list_profiles() if p.id in faces|voices],
                'speaker_ready':bool(self._speaker and self._speaker.ready),
                'enrollment_pending':bool(self._speaker and self._speaker.enrolling),
                'mic_enabled':self._mic_enabled,'capture_paused':self._capture_paused,
                'input_mode':self._input_mode,'mode':self._session_context.mode,
                'scope':self._session_context.context_for_request(self._memory).scope,
                'owner_id':self._session_context.owner_profile_id,
                'owner_present':self._session_context.owner_present,
                'guests':[asdict(g) for g in self._session_context.guests],
                'profiles':[asdict(p) for p in self._memory.list_profiles()],
                'voice_ready':self._stt.is_listening(),'voice_error':self._stt.error,
                'voice_started':self._voice_started,'voice_starting':self._voice_starting,
                'speech_engine':self._config.get('tts',{}).get('engine','voicevox'),
                'speech':self._tts.status() if isinstance(self._tts,TTSEngine) else None,
                'speech_language':'Japanese' if self._bilingual else 'English',
                'translation_language':self._translation_language,
                'initiative_mode':self._initiative.mode,
                'automatic_barge_in':self._barge_in,'pending_topic':bool(self._pending_topic),
                'vision':self._vision.status() if self._vision else None,
                'face_observation':self._face_tracker.get_observation() if self._face_tracker else None,
                'usage':self._usage(),'health':self._health(),
                'persona':str(self._config.get('companion',{}).get('persona') or ''),'brain':self._brain(),'voice':self._voice()}

    def _voicevox_dir(self):
        root=getattr(self,'_voicevox_root',None)
        if root: return Path(root)
        root=Path(self._config.get('tts',{}).get('voicevox_dir','.chassie/voicevox')).expanduser()
        return root if root.is_absolute() else ROOT/root

    def _voice(self):
        style=self._config.get('tts',{}).get('style') or voices.DEFAULT_STYLE
        entry=voices.voice(self._voicevox_dir(),style) or {}
        character=entry.get('character','もち子さん')
        return {'style':style,'character':character,'style_name':entry.get('style','ノーマル'),'credit':voices.credit(character)}

    async def _voices_payload(self):
        if getattr(self,'_voice_sizes',None) is None:
            try: self._voice_sizes=await asyncio.to_thread(voices.pack_sizes)
            except (OSError,ValueError,KeyError): self._voice_sizes={}  # Offline: sizes unknown, list still shown.
        root=self._voicevox_dir()
        try: terms=(root/'models/TERMS.txt').read_text(encoding='utf-8')
        except OSError: terms=''
        return {'type':'voices','voices':voices.catalog(root),'sizes':self._voice_sizes,'terms':terms}

    async def _preview_voice(self):
        await self._cancel_turn()
        chunks=await self._synthesize_sentence('こんにちは。これからこの声でお話しするね。','happy')
        job=await self._begin_playback()
        for pcm in chunks: await self._audio_player.enqueue(pcm,emotion='happy',generation=job)
        self._audio_player.mark_end(job)

    def _brain(self):
        hermes=self._config.get('hermes',{})
        key=PROVIDER_KEYS.get(hermes.get('provider'))
        return {**{k:hermes.get(k) for k in BRAIN_KEYS},'providers':list(PROVIDER_KEYS),'key_name':key,
                'key_saved':bool(key) and key in env_names(self._env_path())}  # Never the key itself.

    def _env_path(self):
        return getattr(self,'_hermes_env_path',None) or Path(os.environ.get('HERMES_HOME','~/.hermes')).expanduser()/'.env'

    def _usage(self):
        usage=getattr(self._hermes,'usage',None)
        usage=dict(usage) if isinstance(usage,dict) else {}
        price=self._config.get('hermes',{}).get('price_per_million') or {}
        if usage and isinstance(price,dict) and price:
            usage['cost']=round((usage.get('prompt_tokens',0)*price.get('input',0)+usage.get('completion_tokens',0)*price.get('output',0))/1e6,4)
        return usage

    def _health(self):
        """True working, False broken, None unknown or switched off."""
        speech=self._tts.status() if isinstance(self._tts,TTSEngine) else None
        vision=self._vision.status() if self._vision else None
        vault=self._vault.status() if self._automatic_memory and self._vault and hasattr(self._vault,'status') else None
        brain=getattr(self._hermes,'healthy',None)
        return {'brain':brain if brain in (True,False) else None,
                'voice':speech.get('ready') if isinstance(speech,dict) else None,
                'ears':(self._stt.is_listening() is True) if self._mic_enabled else None,
                'memory':vault.get('available') if isinstance(vault,dict) else None,
                'eyes':(vision.get('camera',{}).get('available') if vision.get('camera',{}).get('enabled') else None) if isinstance(vision,dict) else None}

    async def _broadcast_settings(self): await self._broadcast_to_ui(self._settings())

    def _save_speech_settings(self):
        self._speech_settings_path.parent.mkdir(parents=True,exist_ok=True)
        pending=self._speech_settings_path.with_suffix('.tmp')
        pending.write_text(json.dumps({'translation_language':self._translation_language,
                                       'initiative_mode':self._initiative.mode}))
        pending.replace(self._speech_settings_path)

    async def handle_control(self,data):
        if not isinstance(data,dict): raise ValueError('Expected an object')
        kind=data.get('type')
        async with self._control_lock:
            if kind in ('select_model','set_model_options'):
                model_id=data.get('model_id')
                if kind=='set_model_options' and model_id!=self._model_selection.state['model_id']:
                    raise ValueError('Model changed. Please use the current model controls.')
                self._model_selection.change({'model_id':model_id} if kind=='select_model' else data)
                if kind=='select_model':
                    self._overlay_sockets.clear()
                    await self._broadcast_avatar_inventory()
                await self._broadcast_to_ui(self._model_selection.payload())
            elif kind=='user_input':
                text=data.get('text')
                if not isinstance(text,str) or not text.strip() or len(text)>8000: raise ValueError('Message must contain 1–8000 characters')
                await self._cancel_turn()
                self._ui_input_queue.put_nowait({'text':text.strip(),'source':'text'})
            elif kind=='set_mic':
                if type(data.get('enabled')) is not bool: raise ValueError('enabled must be boolean')
                self._mic_enabled=data['enabled']
                if not self._mic_enabled and self._speaker:self._speaker.cancel()
                if not self._mic_enabled and self._current_status=='listening':await self._set_status('idle')
                self._purge_inputs(voice_only=True)
                await self._sync_capture()
                if self._mic_enabled and not self._voice_started and (
                    self._voice_start_task is None or self._voice_start_task.done()
                ):
                    self._voice_start_task=asyncio.create_task(self._start_stt())
                    self._tasks.append(self._voice_start_task)
                await self._broadcast_to_ui({'type':'voice_draft_cleared'})
            elif kind=='set_input_mode':
                if data.get('mode') not in ('review','hands_free'): raise ValueError('Invalid input mode')
                self._input_mode=data['mode'];self._stt.invalidate();self._purge_inputs(voice_only=True)
            elif kind=='set_translation_language':
                language=data.get('language')
                if language not in LANGUAGES:raise ValueError('Choose English or Indonesian')
                await self._cancel_turn()
                self._translation_language=language;self._hermes.translation_language=language
                self._save_speech_settings()
            elif kind=='set_persona':
                persona=data.get('persona')
                if not isinstance(persona,str) or not persona.strip() or len(persona)>4000: raise ValueError('Personality must contain 1–4000 characters')
                persona=persona.strip()
                save_local('companion',{'persona':persona},getattr(self,'_local_config_root',ROOT))
                self._config.setdefault('companion',{})['persona']=persona
                self._hermes._persona=' '.join(persona.split())  # Applied from the next reply on.
            elif kind=='set_brain':
                values={k:(data[k].strip() or None) if isinstance(data.get(k),str) else data.get(k) for k in BRAIN_KEYS}  # '' = Hermes default.
                if any(v is not None and not (isinstance(v,str) and re.fullmatch(r'[\w.:/@+-]{1,120}',v)) for v in values.values()):
                    raise ValueError('Provider and model names use only letters, numbers and . : / @ + - _')
                if not values['provider'] and any(values[k] for k in BRAIN_KEYS[1:]):
                    raise ValueError("Choose a provider for these models, or leave every model on Hermes's default")
                save_local('hermes',values,getattr(self,'_local_config_root',ROOT))
                self._config.setdefault('hermes',{}).update(values)
                self._hermes.set_models(**values)
            elif kind=='set_api_key':
                name=PROVIDER_KEYS.get(self._config.get('hermes',{}).get('provider'))
                if not name: raise ValueError('Choose a listed provider first; other providers are set up in Hermes')
                key=data.get('key')
                if not isinstance(key,str) or not re.fullmatch(r'[\x21-\x7e]{8,500}',key.strip()): raise ValueError('That does not look like an API key')
                await asyncio.to_thread(write_env,self._env_path(),name,key.strip())
            elif kind=='test_brain':
                started=time.monotonic()
                try:
                    await self._hermes.complete_once('Reply with the single word OK.','Test',background=False)
                    return {'type':'brain_test','ok':True,'seconds':round(time.monotonic()-started,1)}
                except RuntimeError as exc: return {'type':'brain_test','ok':False,'error':str(exc)[:250]}
            elif kind=='list_voices':
                return await self._voices_payload()
            elif kind=='download_voice':
                if data.get('accept_terms') is not True: raise ValueError('Accept the VOICEVOX terms before downloading a voice')
                pack=data.get('pack')
                if pack not in {v['pack'] for v in voices.catalog(self._voicevox_dir())}: raise ValueError('Unknown voice pack')
                try: await asyncio.to_thread(voices.download,self._voicevox_dir(),pack)
                except (OSError,subprocess.SubprocessError) as exc: raise ValueError('The voice could not be downloaded; check the connection and try again') from exc
                return await self._voices_payload()
            elif kind=='set_voice':
                style=data.get('style')
                entry=voices.voice(self._voicevox_dir(),style) if type(style) is int else None
                if not entry: raise ValueError('Unknown voice')
                if not entry['installed']: raise ValueError('Download this voice first')
                save_local('tts',{'style':style},getattr(self,'_local_config_root',ROOT))
                self._config.setdefault('tts',{})['style']=style
                await self._tts.set_style(style)
                try: await self._preview_voice()
                except RuntimeError as exc: raise ValueError(f'Voice saved, but the sample could not play: {exc}') from exc
            elif kind in ('check_update','apply_update'):
                result=await asyncio.to_thread(updates.check if kind=='check_update' else updates.apply,getattr(self,'_update_root',ROOT))
                await self._broadcast_to_ui({'type':'update',**result})
                if result.get('updated'): await self._broadcast_to_ui({'type':'restart'})  # The desktop app quits; launch.py starts it again.
            elif kind=='set_initiative_mode':
                await self._set_initiative_mode(data.get('mode'))
                self._save_speech_settings()
            elif kind in ('stop','clear_history'):
                await self._cancel_turn(clear=kind=='clear_history')
                if kind=='clear_history':
                    await self._broadcast_to_ui({'type':'history_cleared'})
                    await self._broadcast_to_ui(self._sessions_message())
            elif kind=='list_sessions':
                await self._broadcast_to_ui(self._sessions_message())
            elif kind=='delete_reminder':
                if not self._personal_scope(): raise ValueError('Reminders are only available when you are alone with Chassie')
                self._reminders.delete(data.get('reminder_id'))
                await self._broadcast_to_ui(self._sessions_message())
            elif kind in ('open_session','delete_session'):
                if not self._personal_scope(): raise ValueError('Chat history is only available when you are alone with Chassie')
                session_id=data.get('session_id')
                if kind=='open_session':
                    await self._cancel_turn()
                    self._open_session(session_id)
                    await self._broadcast_to_ui(self._history_snapshot())
                else:
                    if session_id==self._hermes.session_id:
                        await self._cancel_turn(clear=True)
                        await self._broadcast_to_ui({'type':'history_cleared'})
                    self._sessions.delete(session_id)
                await self._broadcast_to_ui(self._sessions_message())
            elif kind=='resume_topic':
                topic=self._pending_topic
                if topic:
                    await self._cancel_turn()
                    self._ui_input_queue.put_nowait({'text':'Please continue answering my previous question: '+topic,'source':'text'})
            elif kind=='preview_emotion':
                if self._current_status in ('thinking','speaking'): raise ValueError('Stop the current reply before previewing expressions')
                name=data.get('emotion')
                info=self._avatar_capabilities()['emotions'].get(name)
                if info is None: raise ValueError('Unknown expression')
                if not info['available']: raise ValueError('Connect a ready avatar renderer before previewing')
                self._avatar_state['emotion']=name;await self._broadcast_avatar()
            elif kind=='avatar_inventory':
                return {'type':'avatar_inventory','capabilities':self._avatar_capabilities()}
            elif kind=='enroll_person':
                if data.get('consent') is not True:raise ValueError('Ask this person for permission before saving their face or voice')
                name=bounded_text(data.get('name'),'name',100)
                face=data.get('face') is True;voice=data.get('voice') is True
                if not face and not voice:raise ValueError('Choose face, voice, or both')
                if face and not self._vision:raise ValueError('Enable the camera before saving a face')
                if voice and not (self._speaker and self._speaker.ready):raise ValueError('Local voice recognition is unavailable')
                embedding=self._vision.enrollment() if face else None
                await self._cancel_turn(clear=True)
                person=next((p for p in self._memory.list_profiles() if p.name.casefold()==name.casefold()),None)
                if person is None:person=self._memory.create_profile(name,consent=True)
                if self._session_context.owner_profile_id is None and len(self._memory.list_profiles())==1:
                    self._session_context.set_owner(person.id)  # The first person introduced is the owner
                if face:self._memory.save_face(person.id,embedding,consent=True)
                if voice:
                    self._speaker.enroll(person.id,consent=True)
                    self._mic_enabled=True
                    await self._sync_capture()
                    if not self._voice_started and (self._voice_start_task is None or self._voice_start_task.done()):
                        self._voice_start_task=asyncio.create_task(self._start_stt());self._tasks.append(self._voice_start_task)
                await self._broadcast_to_ui({'type':'person_enrolled'})
                await self._broadcast_to_ui({'type':'history_cleared'})
                await self._broadcast_to_ui({'type':'notice','text':('Face saved locally. ' if face else '')+('Now speak alone for 3–12 seconds to save your voice. No recording is kept.' if voice else 'Recognition is now automatic.')})
            elif kind=='cancel_enrollment':
                if self._speaker:self._speaker.cancel()
                self._stt.invalidate();self._purge_inputs(voice_only=True)
            elif kind=='forget_person':
                if self._speaker:self._speaker.cancel()
                await self._cancel_turn(clear=True)
                self._memory.delete_face(data.get('person_id'));self._memory.delete_voice(data.get('person_id'))
                await self._broadcast_to_ui({'type':'history_cleared'})
            elif kind=='resume_personal':
                if self._vision and self._visual_guest_reason(self._vision.status()):raise ValueError('Personal memory is paused while someone else is visible or camera presence is unavailable')
                await self._cancel_turn(clear=True)
                for identifier in ('camera-presence','voice-presence'):self._session_context.remove_guest(identifier)
                await self._broadcast_to_ui({'type':'history_cleared'})
            elif kind=='memory_status':
                return {'type':'memory_status',**(await asyncio.to_thread(self._vault.status) if self._vault else {'available':False})}
            elif kind=='list_memories':
                owner=self._session_context.owner_profile_id
                if self._session_context.context_for_request(self._memory).scope!='personal': raise ValueError('Personal memories require a present owner with no guests')
                return {'type':'memories','items':await asyncio.to_thread(self._vault.list) if self._automatic_memory else [asdict(m) for m in self._memory.list_memories(owner)] if owner else []}
            elif kind in ('create_profile','select_profile','delete_profile','add_memory','edit_memory','delete_memory','guest_present','invite_guest','remove_guest','set_mode','set_owner_present'):
                # Context-changing operations invalidate history/output before mutation.
                await self._cancel_turn(clear=True)
                if kind=='create_profile':
                    p=self._memory.create_profile(data.get('name'),consent=data.get('consent'))
                    self._session_context.set_owner(p.id)
                elif kind=='select_profile':
                    profile=data.get('profile_id')
                    if profile is not None and profile not in {p.id for p in self._memory.list_profiles()}: raise ValueError('Unknown profile')
                    self._session_context.set_owner(profile)
                elif kind=='delete_profile':
                    self._memory.delete_profile(data.get('profile_id'))
                    if self._session_context.owner_profile_id==data.get('profile_id'): self._session_context.set_owner(None)
                elif kind in ('add_memory','edit_memory','delete_memory'):
                    if self._session_context.context_for_request(self._memory).scope!='personal': raise ValueError('Personal memory controls require a present owner with no guests')
                    owner=self._session_context.owner_profile_id
                    if not owner: raise ValueError('Select a local profile first')
                    if self._automatic_memory:
                        if kind=='add_memory':
                            if data.get('consent') is not True:raise ValueError('Consent is required to save a memory')
                            await asyncio.to_thread(self._vault.add,data.get('content'))
                        elif kind=='edit_memory':await asyncio.to_thread(self._vault.update,data.get('memory_id'),data.get('content'))
                        else:await asyncio.to_thread(self._vault.delete,data.get('memory_id'))
                    elif kind=='add_memory': self._memory.add_memory(owner,data.get('content'),source='Explicit local user entry',consent=data.get('consent'))
                    elif kind=='edit_memory': self._memory.update_memory(owner,data.get('memory_id'),data.get('content'),source='Explicit local user edit')
                    else: self._memory.delete_memory(owner,data.get('memory_id'))
                elif kind=='guest_present': self._session_context.mark_guest_present(uuid4().hex,data.get('name','Guest'))
                elif kind=='invite_guest': self._session_context.invite_guest(data.get('guest_id'))
                elif kind=='remove_guest': self._session_context.remove_guest(data.get('guest_id'))
                elif kind=='set_mode': self._session_context.set_mode(data.get('mode'))
                else: self._session_context.set_owner_present(data.get('present'))
                await self._broadcast_to_ui({'type':'history_cleared'})
                items=(await asyncio.to_thread(self._vault.list) if self._automatic_memory and kind in ('add_memory','edit_memory','delete_memory') else [])
                await self._broadcast_to_ui({'type':'memories','items':items})
            elif kind=='avatar_window':
                # Placement buttons in the desktop panels; the overlay owns the window, so relay.
                if data.get('action') not in AVATAR_WINDOW_ACTIONS: raise ValueError('Unknown avatar window action')
                await self._broadcast_to_ui({'type':'avatar_window','action':data['action']})
            elif kind=='hello': pass
            else: raise ValueError('Unknown control')
            await self._broadcast_settings()
