"""UI control commands and the settings snapshot broadcast to every client."""
from __future__ import annotations
import asyncio
from dataclasses import asdict
import json
import logging
from uuid import uuid4
from memory.store import bounded_text
from speech.tts_engine import TTSEngine
from brain.bilingual import LANGUAGES

logger=logging.getLogger('orchestrator')


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
                'usage':self._usage(),'health':self._health()}

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
