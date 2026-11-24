"""Async conversation control with cancellable turns and explicit local session scope."""
from __future__ import annotations

import re
import asyncio
import datetime
import json
import logging
from pathlib import Path
import queue
import time
from uuid import uuid4

from aiohttp import web

from audio_analyzer import AudioAnalyzer
from audio_player import AudioPlayer
from companion import MemoryStore, SessionContext
from companion.vault import VaultMemory
from companion import reflection
from companion.reflection import NOTE_DIR as DIARY_DIR
from voice_identity import VoiceIdentity
from hermes_bridge import HermesBridge, ToolProgress
import desktop_grant

# (Japanese speech, translation) spoken when Hermes starts a tool before saying anything.
TOOL_FILLERS={'en':('ちょっと調べてみるね。','Let me check that for you.'),
              'id':('ちょっと調べてみるね。','Bentar, aku cek dulu ya.')}
# Said when the first sentence is slow, so a pause never feels like Chassie froze.
THINKING_FILLERS={'en':('えっとね…','Hmm...'),'id':('えっとね…','Hmm...')}
from stt_engine import STTEngine
from tts_engine import TTSEngine
from speech_chunker import SpeechChunker
from speech_pacing import SpeechPacing
from bilingual import BilingualChunker, LANGUAGES, display_translation, split_first_clause
from avatar import load_manifest
from avatar.manifest import DEFAULT_MANIFEST
from avatar.catalog import ModelCatalog, ModelSelection
from chassie_core.sessions import SessionStore, new_session_id
from chassie_core.reminders import ReminderStore, parse_time
from chassie_core.initiative import PREFIX as INITIATIVE_PREFIX
from face_identity import face_command
from visual_context import VisualContext
from visual_requests import requested_visual_sources
from app_context import active_application

logger=logging.getLogger('orchestrator')
SEMANTIC_MIN=2.0  # z-score vs the whole vault; unrelated queries on the owner's vault topped out near 2.0.

from chassie_core.controls import ControlsMixin
from chassie_core.presence import PresenceMixin
from chassie_core.initiative import InitiativeMixin
from chassie_core.web import WebMixin

class _Chunks(list):
    mouth=None


def _with_mouth(chunks,mouth=None):
    """Sentence audio chunks plus the synthesizer's lip-sync keyframes (sentence-relative)."""
    result=_Chunks(chunks)
    result.mouth=mouth if mouth is not None else next((getattr(c,'mouth',None) for c in chunks
                                                      if getattr(c,'mouth',None)),None)
    return result


class _LookNow(Exception):
    """The model asked to see a source before saying anything: retry the turn with it."""


class _AvatarOutput:
    def __init__(self, owner): self.owner=owner
    async def trigger_emotion(self,emotion):
        self.owner._avatar_state['emotion']=emotion
        await self.owner._broadcast_avatar()
        return True
    async def set_mouth_open(self,value):
        value=float(value)
        self.owner._avatar_state['mouth']=value
        await self.owner._broadcast_avatar()

class Orchestrator(ControlsMixin,WebMixin,PresenceMixin,InitiativeMixin):
    def __init__(self,config,text_mode=False,*,components=None):
        c=components or {}
        self._config=config
        self._bilingual=config.get('tts',{}).get('engine')=='voicevox'; self._text_mode=text_mode; self._running=False
        self._stt_queue=queue.Queue(maxsize=32)
        self._stt=c.get('stt') or STTEngine(config,self._stt_queue)
        self._hermes=c.get('hermes') or HermesBridge(config)
        self._tts=c.get('tts') or TTSEngine(config)
        self._audio_player=c.get('player') or AudioPlayer(config)
        self._audio_analyzer=c.get('analyzer') or AudioAnalyzer(sample_rate=config['audio']['output_sample_rate'])
        self._face_tracker=c.get('face')
        self._memory=MemoryStore(config.get('companion',{}).get('memory_path',str(Path(__file__).parent/'.chassie/memory.sqlite')))
        self._vision=c.get('vision')
        if self._vision is None and any(config.get('vision',{}).get(key,False) for key in ('camera_enabled','screen_enabled')):
            self._vision=VisualContext(config,self._memory)
        self._turn_images=[]
        self._turn_vision=None
        self._turn_app=None
        self._turn_initiative=False;self._turn_skipped=False
        self._screen_unchanged=False
        self._look_now=None;self._looked=False  # Model-chosen look before answering (once per turn)
        self._previous_user_text=''
        self._semantic=None
        self._transcripts=Path(config.get('companion',{}).get('memory_path',str(Path(__file__).parent/'.chassie/memory.sqlite'))).parent/'transcripts'
        self._face_command_result=None
        self._session_context=SessionContext()
        self._automatic_memory=config.get('companion',{}).get('automatic_memory',False) is True
        # False: other faces on camera do not pause personal memory, history or initiatives.
        self._guest_privacy=config.get('companion',{}).get('guest_privacy',False) is True
        self._vault=c.get('vault')
        self._speaker=c.get('speaker')
        self._owner_alone_since=None
        if self._automatic_memory:
            owner=config.get('hermes',{}).get('personal_memory_profile_id')
            if owner in {p.id for p in self._memory.list_profiles()}:self._session_context.set_owner(owner)
            self._vault=self._vault or VaultMemory()
            self._speaker=self._speaker or VoiceIdentity(self._memory,presence=lambda:self._vision.status() if self._vision else {})
            self._stt.speaker_identity=self._speaker
        self._catalog=ModelCatalog()
        selection_path=Path(config.get('companion',{}).get('memory_path',str(Path(__file__).parent/'.chassie/memory.sqlite'))).parent/'model-selection.json'
        self._model_selection=ModelSelection(self._catalog,selection_path)
        self._subtitle=None
        self._ui_sockets=set()
        self._overlay_sockets={}
        self._avatar_manifest=load_manifest(config.get('avatar',{}).get('expression_manifest',DEFAULT_MANIFEST))
        self._ui_input_queue=asyncio.Queue(maxsize=16)
        self._current_status='idle';self._turn_task=None;self._tasks=[]
        self._listening_until=0.
        self._generation=0;self._spoken='';self._pending_topic=None
        self._stream_view=None
        self._turn_metrics={}
        self._mic_enabled=not text_mode
        self._voice_started=False;self._voice_starting=False;self._voice_start_task=None
        self._capture_paused=False
        self._last_backchannel=0.0
        # Full duplex only when echo_cancel.enable() routed audio through PipeWire AEC.
        self._barge_in=config.get('conversation',{}).get('barge_in') is True
        self._speaking_since=0.0
        self._input_mode=config.get('conversation',{}).get('input_mode','review')
        if self._input_mode not in ('review','hands_free'): raise ValueError('Invalid input mode')
        self._speech_settings_path=selection_path.with_name('speech-settings.json')
        self._sessions=SessionStore(selection_path.with_name('sessions'))
        self._reminders=ReminderStore(selection_path.with_name('reminders.json'))
        self._summary_tasks=set()
        self._translation_language=config.get('tts',{}).get('translation_language','en')
        try:saved=json.loads(self._speech_settings_path.read_text())
        except (OSError,ValueError):saved={}
        if not isinstance(saved,dict):saved={}
        self._translation_language=saved.get('translation_language',self._translation_language)
        self._init_initiative(saved.get('initiative_mode'))
        self._thinking_filler=config.get('conversation',{}).get('thinking_filler_seconds',2.5)
        if self._translation_language not in LANGUAGES:self._translation_language='en'
        self._hermes.translation_language=self._translation_language
        self._avatar_state={'emotion':'neutral','mouth':0.0}
        self._avatar=_AvatarOutput(self)
        self._control_lock=asyncio.Lock()
        self._web_runner=None
        self._web_app=web.Application(client_max_size=16384)
        self._web_app.router.add_get('/ws',self._handle_ui_websocket)
        self._web_app.router.add_get('/api/status',self._handle_status)
        self._web_app.router.add_get('/api/models',self._handle_models)
        self._web_app.router.add_get('/api/models/{model_id}/model.json',self._handle_model_manifest)
        self._web_app.router.add_get('/api/models/{model_id}/assets/{asset:.*}',self._handle_model_asset)
        self._web_app.router.add_get('/',self._handle_index)
        self._web_app.router.add_static('/',path=str(Path(__file__).parent/'ui'))

    async def start(self):
        self._running=True
        await self._hermes.connect()
        self._resume_latest_session()
        self._tts.load_model()
        self._audio_player.start(loop=asyncio.get_running_loop(),avatar=self._avatar,analyzer=self._audio_analyzer)
        # Start web controls before expensive device/model loading.
        self._web_runner=web.AppRunner(self._web_app);await self._web_runner.setup()
        cfg=self._config.get('ui',{})
        await web.TCPSite(self._web_runner,'127.0.0.1',cfg.get('port',8000)).start()
        if isinstance(self._tts,TTSEngine):self._tts.start()
        self._tasks=[asyncio.create_task(self._stt_poll_loop()),asyncio.create_task(self._face_monitor_loop()),
                     asyncio.create_task(self._initiative_loop())]
        if self._automatic_memory and self._vault and getattr(self._vault,'store',None) is not None:
            self._tasks+=[asyncio.create_task(self._memory_warmup()),asyncio.create_task(self._reflection_loop())]
        if self._vision:
            self._vision.start()
            self._tasks.append(asyncio.create_task(self._vision_status_loop()))
        if not self._text_mode:
            self._voice_start_task=asyncio.create_task(self._start_stt())
            self._tasks.append(self._voice_start_task)
        if self._vision and self._vision.camera_enabled:
            # One camera owner. Its detector also supplies the existing guest guard.
            self._face_tracker=self._vision
        elif 'vision' not in self._config and self._config.get('face_tracker',{}).get('enabled',False):
            try:
                if self._face_tracker is None:
                    from face_tracker import FaceTracker
                    self._face_tracker=FaceTracker(self._config)
                self._face_tracker.start()
            except Exception as exc: logger.warning('Face tracker unavailable: %s',type(exc).__name__)
        if self._automatic_memory and self._vault and getattr(self._vault,'store',True) is None:
            logger.warning('Memory is off: %s (vault path in ~/.hermes/chassie.json)',self._vault.error)
        logger.info('Chassie controls: http://127.0.0.1:%s',cfg.get('port',8000))
        await self._main_loop()

    async def _start_stt(self):
        if self._voice_started or self._voice_starting: return
        self._voice_starting=True
        try:
            await asyncio.to_thread(self._stt.start)
            self._voice_started=True
        except Exception as exc:
            self._mic_enabled=False
            await self._broadcast_to_ui({'type':'notice','text':f'Voice input unavailable ({type(exc).__name__}). Text chat is available.'})
        finally:
            self._voice_starting=False
        await self._broadcast_settings()

    async def _main_loop(self):
        while self._running:
            async with self._control_lock:
                if not self._turn_task or self._turn_task.done():
                    try: item=self._ui_input_queue.get_nowait()
                    except asyncio.QueueEmpty: item=None
                    if item and item.get('source')=='voice' and (not self._mic_enabled or self._capture_paused or item.get('epoch')!=self._stt.epoch):
                        item=None
                    if item: self._turn_task=asyncio.create_task(self._run_turn(item))
            await asyncio.sleep(.02)

    def _vault_recall(self,query):
        """Owner-only Obsidian recall done locally: Hermes no longer forwards Chassie's memory key.

        Always: the owner's profile note, the latest diary note (open loops to follow up)
        and the newest facts Chassie saved. Then up to three other notes ranked by keyword
        and local semantic similarity (reciprocal rank fusion), one chunk per note.
        """
        if not (self._automatic_memory and self._vault): return []
        try:
            rows=self._vault.call('list',400)
            owner=next((p.name for p in self._memory.list_profiles()
                        if p.id==self._session_context.owner_profile_id),None)
            found=[]
            if owner:
                found+=[r for r in rows if r['path'].casefold()==f'people/{owner}.md'.casefold()][:1]
            diaries=sorted((r for r in rows if r['path'].startswith(DIARY_DIR+'/')),key=lambda r:r['path'],reverse=True)
            if diaries and diaries[0]['path'][len(DIARY_DIR)+1:len(DIARY_DIR)+11]>=(datetime.date.today()-datetime.timedelta(days=3)).isoformat():
                found.append(diaries[0])
            found+=sorted((r for r in rows if r.get('kind')=='user_statement'),
                          key=lambda r:r.get('updated',''),reverse=True)[:6]
            if query:
                taken={r['path'] for r in found};fused={};best={}
                lists=[self._vault.call('search',query,10)]
                if self._semantic is not None:
                    # Only chunks that clearly stand out; keyword hits still rank alongside (RRF).
                    lists.append([r for score,r in self._semantic.rank(query,rows,10) if score>=SEMANTIC_MIN])
                for ranked in lists:
                    for position,r in enumerate(ranked):
                        if r['path'] in taken: continue
                        fused[r['path']]=fused.get(r['path'],0)+1/(60+position)
                        best.setdefault(r['path'],r)
                found+=[best[p] for p in sorted(fused,key=fused.get,reverse=True)[:3]]
        except (ValueError,AttributeError,TypeError,KeyError,OSError) as exc:
            if not getattr(self,'_vault_warned',False):
                self._vault_warned=True
                logger.warning('Memory recall unavailable: %s',exc)
            return []
        return [{'content':str(r.get('content',''))[:600],'source':'obsidian:'+str(r.get('path',''))} for r in found]

    def _others_in_view(self):
        if self._guest_privacy or not (self._vision and getattr(self._vision,'camera_enabled',False)): return None
        try: status=self._vision.status()
        except Exception: return None
        if not isinstance(status,dict) or not status.get('camera',{}).get('available'): return None
        identity=status.get('identity',{})
        owner=self._session_context.owner_profile_id
        names=[m.get('name') for m in identity.get('matches',[]) if m.get('profile_id')!=owner and m.get('name')]
        count=max(0,int(identity.get('face_count',0) or 0)-1)
        return {'count':max(count,len(names)),'recognized':names} if count or names else None

    def _context_text(self,query=''):
        context=self._session_context.context_for_request(self._memory)
        payload={'scope':context.scope,'mode':context.mode,
                 'memories':(self._vault_recall(query) if context.scope=='personal' else []) if self._automatic_memory
                            else [{'content':m.content,'source':m.source} for m in context.memories[-8:]],
                 'shared_notes':list(context.shared_notes[-4:]),
                 'local_time':datetime.datetime.now().astimezone().strftime('%A %Y-%m-%d %H:%M %Z')}
        if context.scope=='personal':
            recap=self._previous_chat()
            if recap: payload['previous_chat']={**recap,'note':'Recap of the last earlier conversation; '
                'bring it up only if it fits, as something you remember.'}
        if context.scope=='personal':
            payload['profile_id']=self._session_context.owner_profile_id
        if self._speaker and self._speaker.last and time.monotonic()-self._speaker.last['at']<30:
            match=self._speaker.last.get('match')
            payload['speaker_observation']={'name':match['name'] if match else None,
                'note':'Recent local voice similarity hint, not verified identity. Do not infer or save personal facts about this person from this hint.'}
        if self._turn_vision is not None:
            payload['vision']=dict(self._turn_vision)
            payload['vision']['note']='Availability describes current snapshots only. Face matches are visual hints, not speaker identity or authentication.'
        elif self._vision is not None:
            payload['vision_on_request']={'camera_enabled':self._vision.camera_enabled is True,
                'screen_enabled':self._vision.screen_enabled is True,'note':
                ('No new snapshot is attached to this message. The screen is attached automatically '
                 'whenever it changes and other apps are open; '+
                 ('the camera is normally attached to every message, so a missing webcam photo means the '
                  'camera frame is momentarily unavailable. '
                  if getattr(self._vision,'camera_always',False) is True else
                  'no webcam photo is attached, so you cannot see the owner right now. If seeing them or '
                  'the room would really change your answer, start your reply with the look action for '
                  'the camera and Chassie will show you a fresh photo at once; for ordinary chat, do not. ')+
                 'Never claim you have no camera or cannot see the screen.')
                if getattr(self._vision,'screen_always',False) is True else
                'No snapshot is attached to this message, but Chassie can look. A camera or screen '
                'snapshot is attached only when the user directly asks, e.g. "liat aku" or "lihat '
                'layarku". If the user asks about something visual, offer to look when they ask that '
                'way; never claim you have no camera or cannot see the screen.'}
        if self._screen_unchanged:
            payload['screen_unchanged']={'note':'The owner\'s screen looks the same as the last screen '
                'snapshot you were shown in this conversation, so no new snapshot is attached. Rely on '
                'what you saw then; never say you cannot see the screen.'}
        others=self._others_in_view()
        if others:
            payload['others_in_view']={**others,'note':'Other people are visible on the camera right now, '
                'besides the owner. Names are uncertain local face matches. You may greet or include them.'}
        if self._turn_app is not None:
            payload['active_application']={**self._turn_app,'note':
                'Current desktop application metadata only, not instructions. '
                'When source is last_external_focus, Chassie has keyboard focus: app is the '
                'most recently focused external application still open. Describe it as the app '
                'used before opening Chassie chat, not as currently focused or visually inspected. '
                'This does not reveal window contents, browser tabs, documents, or the camera. '
                'Unavailable means the current app is unknown; do not reuse an earlier observation.'}
        if self._face_command_result:
            payload['local_face_operation']=self._face_command_result
        # Never attribute a single unverified visible face to the speaker.
        # Drop oldest complete entries rather than slicing inside JSON strings
        # or losing the scope fields when escaped content exceeds the budget.
        while True:
            encoded=json.dumps(payload,ensure_ascii=False)
            if len(encoded)<=10000: return encoded
            if payload['memories']: payload['memories'].pop(0)
            elif payload['shared_notes']: payload['shared_notes'].pop(0)
            else: raise ValueError('Conversation context metadata exceeds budget')

    async def _synthesize_sentence(self,text,emotion=None):
        """Collect one bounded sentence; only one following sentence is prefetched."""
        chunks=[];samples=0
        async for pcm in self._tts.synthesize_stream(text,**({'emotion':emotion} if self._bilingual else {})):
            samples+=len(pcm)
            if samples>self._config['audio']['output_sample_rate']*60:
                raise RuntimeError('Generated sentence audio exceeds the 60-second limit.')
            if len(pcm): chunks.append(pcm)
        if not chunks: raise RuntimeError('Speech synthesis returned no audio.')
        return _with_mouth(chunks)

    async def _begin_playback(self):
        # begin_utterance may wait for a device lock. Shield the worker task so
        # cancellation can join it and discard a generation created after Stop.
        pending=asyncio.create_task(asyncio.to_thread(self._audio_player.begin_utterance))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            await asyncio.gather(pending,return_exceptions=True)
            await asyncio.to_thread(self._audio_player.cancel_utterance)
            raise

    async def _produce_speech(self,text,generation,sentences,started):
        chunker=BilingualChunker(self._translation_language) if self._bilingual else SpeechChunker()
        first_pair=True
        self._turn_sentences=0
        self._turn_memories=[]
        self._turn_skipped=False
        async def put(sentence):
            nonlocal first_pair
            self._turn_sentences+=1
            self._turn_metrics.setdefault('first_sentence_seconds',time.monotonic()-started)
            parts=split_first_clause(sentence[2]) if self._bilingual and first_pair else [None]
            first_pair=False
            if len(parts)==1: await sentences.put(sentence);return
            # Only the reply's first sentence waits on synthesis; later ones are prefetched during playback.
            emotion,translation=sentence[:2]
            await sentences.put((emotion,translation,parts[0],'head'))
            await sentences.put((emotion,translation,parts[1],'tail'))
        received_length=0
        # Initiatives recall only profile + recent facts; their cue text is not a search query.
        context=self._context_text('' if self._turn_initiative else ' '.join(filter(None,(self._previous_user_text,text))))
        # Desktop control (agent-desktop) is allowed only while the owner is present with no guests.
        owner_turn=json.loads(context).get('scope')=='personal'
        if owner_turn: desktop_grant.grant(self._hermes._stream_timeout+5)
        else: desktop_grant.revoke()
        stream=self._hermes.stream_message(text,context=context,mode=self._session_context.mode,
                                          **({'images':self._turn_images} if self._turn_images else {}))
        async def filler():
            await asyncio.sleep(self._thinking_filler)
            if not self._turn_sentences and generation==self._generation:
                phrase=THINKING_FILLERS[self._translation_language if self._bilingual else 'en']
                await put(('thinking',phrase[1],phrase[0]) if self._bilingual else ('thinking',phrase[1]))
        filler_task=(asyncio.create_task(filler()) if self._thinking_filler and not self._turn_initiative
                     else None)
        try:
            async for delta in stream:
                if generation!=self._generation: return
                if isinstance(delta,ToolProgress):
                    await self._on_tool_progress(delta,chunker,put,text)
                    continue
                self._turn_metrics.setdefault('first_text_seconds',time.monotonic()-started)
                received_length+=len(delta)
                if received_length>30000: raise RuntimeError('Response too long')
                for sentence in chunker.feed(delta): await self._route(sentence,text,put)
            self._turn_metrics['hermes_complete_seconds']=time.monotonic()-started
            for sentence in chunker.finish(): await self._route(sentence,text,put)
            await sentences.put(None)
        except _LookNow:
            await sentences.put(None)
        except (ValueError, RecursionError) as exc:
            if not self._bilingual: raise
            raise RuntimeError(f'The reply did not contain valid Japanese speech and {LANGUAGES[self._translation_language]} translations. Please retry.') from exc
        finally:
            if filler_task: filler_task.cancel()
            await stream.aclose()
            if owner_turn: desktop_grant.revoke()

    async def _route(self,sentence,text,put):
        """Send one parsed line where it belongs: memory, action, silence, or speech."""
        kind=sentence[0]
        if kind=='memory': self._turn_memories.append((sentence[1],sentence[2] if len(sentence)>2 else {}))
        elif kind=='action': await self._run_model_action(text,*sentence[1:])
        elif kind=='skip': self._turn_skipped=True
        else: await put(sentence)

    async def _on_tool_progress(self,event,chunker,put,text):
        """Speak what was said so far while Hermes works, and show what it is doing."""
        if event['status']!='running': return
        if hasattr(chunker,'allow_tool_narration'): chunker.allow_tool_narration()
        for sentence in chunker.flush(): await self._route(sentence,text,put)
        if not self._turn_sentences:
            # The model went straight to a tool: say a short filler so the wait is not silent.
            filler=TOOL_FILLERS[self._translation_language if self._bilingual else 'en']
            await put(('thinking',filler[1],filler[0]) if self._bilingual else ('thinking',filler[1]))
        if self._current_status!='speaking': await self._set_status('thinking')

    async def _next_speech(self,sentences):
        item=await sentences.get()
        if item is None: return None
        emotion,sentence=item[:2]
        speech=item[2] if self._bilingual else sentence
        part=item[3] if len(item)>3 else None
        return emotion,sentence,await self._synthesize_sentence(speech,emotion),part,speech

    async def _play_speech(self,sentences,generation,started):
        prefetch=None
        pacing=SpeechPacing(self._config['audio']['output_sample_rate'])
        try:
            prefetch=asyncio.create_task(self._next_speech(sentences))
            first=True
            while True:
                item=await prefetch
                prefetch=None
                if item is None:
                    if first and not self._turn_skipped and self._look_now is None: raise RuntimeError('Hermes returned no speakable text.')
                    break
                emotion,sentence,chunks,part,speech=item
                if generation!=self._generation: return
                delay=pacing.delay(chunks,now=time.monotonic())
                if delay:
                    await asyncio.sleep(delay)
                    if generation!=self._generation: return
                chunks=_with_mouth(pacing.smooth(chunks),getattr(chunks,'mouth',None))
                if first:
                    self._turn_metrics['first_pcm_seconds']=time.monotonic()-started
                    self._speaking_since=time.monotonic()
                    if not self._barge_in:
                        # Without echo cancellation the microphone would hear Chassie, so stay half-duplex.
                        self._capture_paused=True
                        await self._sync_capture()
                        self._purge_inputs(voice_only=True)
                    await self._broadcast_settings()
                    await self._set_status('speaking')
                    self._audio_analyzer.reset()
                    first=False
                job=await self._begin_playback()
                if generation!=self._generation: return
                if part!='tail':
                    self._subtitle={'type':'subtitle','text':sentence,'generation':generation}
                    await self._broadcast_to_ui(self._subtitle)
                prefetch=asyncio.create_task(self._next_speech(sentences))
                mouth_offset=0
                for chunk_index,pcm in enumerate(chunks):
                    if generation!=self._generation: return
                    lips={'mouth':chunks.mouth,'mouth_offset':mouth_offset} if getattr(chunks,'mouth',None) else {}
                    mouth_offset+=len(pcm)
                    if not await self._audio_player.enqueue(pcm,emotion=emotion,generation=job,**lips):
                        raise RuntimeError('Audio playback was interrupted.')
                    self._turn_metrics.setdefault('first_audio_queued_seconds',time.monotonic()-started)
                    if chunk_index==0 and part!='tail':
                        # Show the sentence as its audio starts. Keep _spoken
                        # separate: only drained sentences count as fully spoken.
                        self._stream_view['text']+=(' ' if self._stream_view['text'] else '')+f'[{emotion}] {sentence}'
                        await self._broadcast_stream()
                self._audio_player.mark_end(job)
                await self._audio_player.wait_until_done(job)
                if generation!=self._generation: return
                if part=='head':
                    # Keep the subtitle; the tail continues this sentence after a comma-length pause.
                    pacing.completed(speech,chunks,now=time.monotonic())
                    continue
                pacing.completed(sentence,chunks,now=time.monotonic())
                self._spoken+=' '+sentence
                await self._avatar.set_mouth_open(0)
                self._subtitle=None
                await self._broadcast_to_ui({'type':'subtitle','text':'','generation':generation})
        finally:
            if prefetch is not None:
                prefetch.cancel()
                await asyncio.gather(prefetch,return_exceptions=True)

    async def _broadcast_stream(self):
        if self._stream_view and self._stream_view['text']:
            await self._broadcast_to_ui({'type':'chat_stream',**{k:v for k,v in self._stream_view.items() if k!='user_text'}})

    async def _run_turn(self,item):
        generation=self._generation
        self._spoken=''
        text=item['text']
        self._turn_initiative=item.get('source')=='initiative'
        self._note_activity(user=not self._turn_initiative)
        if not self._turn_initiative: self._pending_topic=text
        self._stream_view={'id':uuid4().hex,'user_text':text,'text':'','done':False,'interrupted':False}
        self._turn_metrics={}
        self._turn_images=[]
        self._turn_vision=None
        self._turn_app=None
        self._face_command_result=None
        started=time.monotonic()
        if isinstance(self._tts,TTSEngine):self._tts.begin_turn()
        tasks=[]
        completed=False
        try:
            if self._config.get('app_context',{}).get('enabled',False):
                self._turn_app=await asyncio.to_thread(active_application)
            if self._vision:
                requested=set(item.get('visual',())) if self._turn_initiative else requested_visual_sources(text)
                if getattr(self._vision,'screen_always',False) is True and getattr(self._vision,'screen_enabled',False):
                    # Send the screen only when it changed since the model last saw it. Explicit
                    # requests, screen-change initiatives and look-again always include it.
                    reason=item.get('reason')
                    automatic=(reason in ('app','quiet')) if self._turn_initiative else 'screen' not in requested
                    if automatic:
                        has_content=getattr(self._vision,'screen_has_content',None)
                        if has_content is not None and not await asyncio.to_thread(has_content):
                            requested.discard('screen')  # Only Chassie is on screen: nothing to show.
                        elif self._vision.screen_changed(): requested.add('screen')
                        else:
                            requested.discard('screen');self._screen_unchanged=True
                if (getattr(self._vision,'camera_always',False) is True and self._vision.camera_enabled is True
                        and not self._turn_initiative):
                    requested.add('camera')
                if requested:
                    status=self._attach_visual(requested)
                else:
                    status=self._vision.status()
                reason=self._visual_guest_reason(status)
                if reason and not any(g.id=='camera-presence' for g in self._session_context.guests):
                    # Enforce scope before any request; the background monitor
                    # alone leaves a race between capture and its next tick.
                    self._hermes.clear_history()
                    self._session_context.mark_guest_present('camera-presence',reason)
                    await self._broadcast_to_ui({'type':'history_cleared'})
                    await self._broadcast_to_ui({'type':'memories','items':[]})
                    await self._broadcast_settings()
            if not self._turn_initiative:
                await self._broadcast_to_ui({'type':'chat','role':'user','text':text})
            await self._set_status('thinking')
            command=None if self._turn_initiative else face_command(text)
            if command:
                self._face_command_result=self._apply_face_command(*command)
                if self._turn_vision:
                    self._turn_vision={**self._turn_vision,'identity':{**self._turn_vision.get('identity',{}),'matches':[]}}
                await self._broadcast_to_ui({'type':'notice','scope':'chat','text':self._face_command_result})
            self._looked=False
            while True:
                self._look_now=None
                sentences=asyncio.Queue(maxsize=8)
                tasks=[asyncio.create_task(self._produce_speech(text,generation,sentences,started)),
                       asyncio.create_task(self._play_speech(sentences,generation,started))]
                await asyncio.gather(*tasks)
                if generation!=self._generation: return
                if self._look_now is None: break
                # Hermes chose to look before answering: forget the attempt and ask again with the image.
                logger.info('Model looked at the %s before answering',self._look_now)
                self._hermes.discard_response()
                self._looked=True
                self._attach_visual({f['source'] for f in self._turn_images}|{self._look_now})
            if self._turn_skipped and not self._turn_sentences:
                self._hermes.discard_response()
                logger.info('Initiative skipped by the model')
            else:
                self._hermes.complete_response()
                self._log_transcript(text)
            if not self._turn_initiative: self._previous_user_text=text[-300:]
            self._pending_topic=None
            completed=True
            await self._save_turn_memories(text)
            self._turn_metrics['complete_seconds']=time.monotonic()-started
            logger.info('Streaming turn timings (seconds): %s',{k:round(v,3) for k,v in self._turn_metrics.items()})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for task in tasks: task.cancel()
            await asyncio.to_thread(self._audio_player.cancel_utterance)
            await asyncio.gather(*tasks,return_exceptions=True)
            await self._audio_player.flush_effects()
            self._hermes.interrupt_response(self._spoken)
            logger.warning('Reply failed after %.3fs: %s (%s); timings=%s',time.monotonic()-started,
                           type(exc).__name__,str(exc)[:200],{k:round(v,3) for k,v in self._turn_metrics.items()})
            await self._broadcast_to_ui({'type':'notice','scope':'chat',
                                        'stream_id':self._stream_view['id'],'text':str(exc)[:250],'retry_text':text})
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            self._save_session()
            self._turn_images=[]
            self._turn_vision=None
            self._turn_app=None
            self._face_command_result=None
            self._screen_unchanged=False
            self._stream_view['done']=True
            self._stream_view['interrupted']=not completed
            self._note_activity()
            if generation==self._generation:
                self._subtitle=None
                await self._broadcast_to_ui({"type":"subtitle","text":"","generation":generation})
                await self._broadcast_stream()
                await asyncio.to_thread(self._audio_player.cancel_utterance)
                await self._audio_player.flush_effects()
                await self._avatar.set_mouth_open(0)
                self._capture_paused=False
                await self._sync_capture()
                await self._set_status('idle' if not self._mic_enabled else 'listening')
                await self._broadcast_settings()

    def _attach_visual(self,requested):
        """Attach fresh frames for the requested sources to this turn; return the vision status."""
        frames,status=self._vision.request_context()
        self._turn_images=[frame for frame in frames if frame['source'] in requested]
        if any(frame['source']=='screen' for frame in self._turn_images) and hasattr(self._vision,'mark_screen_sent'):
            self._vision.mark_screen_sent()
        self._turn_vision={source:status.get(source,{}) for source in requested}
        if 'camera' in requested:
            self._turn_vision['identity']=status.get('identity',{})
        return status

    def _purge_inputs(self,voice_only=False):
        keep=[]
        while not self._ui_input_queue.empty():
            item=self._ui_input_queue.get_nowait()
            if voice_only and item.get('source')!='voice': keep.append(item)
        for item in keep: self._ui_input_queue.put_nowait(item)

    async def _run_model_action(self,user_text,action,name):
        """Run a model-requested action before any speech; a failure stops the reply."""
        if action=='remind':
            if not self._personal_scope(): return  # Only the owner sets reminders.
            try:
                item=self._reminders.add(name['text'],parse_time(name['at']),name.get('repeat'))
            except (ValueError,TypeError,KeyError) as exc:
                logger.warning('Reminder not set: %s',exc);return
            when=datetime.datetime.fromisoformat(item['at']).strftime('%a %d %b %H:%M')
            await self._broadcast_to_ui({'type':'notice','scope':'chat','text':f"Reminder set: {item['text']} · {when}"
                                         +(f" ({item['repeat']})" if item.get('repeat') else '')})
            await self._broadcast_to_ui(self._sessions_message())
            return
        if action=='look':
            attached={f['source'] for f in self._turn_images}
            if (not self._turn_sentences and not getattr(self,'_looked',False) and name not in attached
                    and self._vision and getattr(self._vision,name+'_enabled',False)):
                self._look_now=name
                raise _LookNow()
            self._request_look(name);return
        if self._face_command_result is not None:
            return  # The local command parser already handled this message.
        # Privacy guard: never enroll or delete a face unless the user's own message is about faces.
        if not re.search(r'\b(?:wajah\w*|muka\w*|faces?)\b',user_text,re.IGNORECASE):
            logger.warning('Ignored model action %s without a face request',action)
            return
        try:self._face_command_result=self._apply_face_command('remember' if action=='remember_face' else 'forget',name)
        except ValueError as exc:raise RuntimeError(str(exc)) from exc  # Keep the real reason visible.
        await self._broadcast_to_ui({'type':'notice','scope':'chat','text':self._face_command_result})

    def _log_transcript(self,text):
        """Owner-only local log that feeds the daily reflection; guests are never written."""
        if not (self._automatic_memory and self._stream_view and self._stream_view.get('text')): return
        if self._session_context.context_for_request(self._memory).scope!='personal': return
        try: reflection.log_turn(self._transcripts,text,self._stream_view['text'],initiative=self._turn_initiative)
        except OSError as exc: logger.warning('Transcript not saved: %s',exc)

    async def _memory_warmup(self):
        """Load the semantic model and embed the vault off the event loop."""
        try:
            from companion.semantic import SemanticIndex
            cache=self._transcripts.parent/'semantic-cache.npz'
            index=await asyncio.to_thread(SemanticIndex,cache_path=cache)
            rows=await asyncio.to_thread(self._vault.call,'list',400)
            added=await asyncio.to_thread(index.sync,rows)
            self._semantic=index
            logger.info('Semantic memory indexed %d new chunk(s) on %s',added,'GPU' if index.on_gpu else 'CPU')
        except Exception as exc:
            logger.warning('Semantic memory off, keyword recall only: %s',exc)

    async def _reflection_loop(self):
        """Write yesterday's diary once Chassie is idle; retries later after a failure."""
        await asyncio.sleep(60)
        while self._running:
            try:
                busy=(self._turn_task and not self._turn_task.done()) or self._current_status not in ('idle','listening')
                days=[] if busy else reflection.pending_days(self._transcripts,self._vault.path)
                if days:
                    day=days[0]
                    reply=await self._hermes.complete_once(reflection.SYSTEM,
                        f'Date: {day.isoformat()}\n\n'+reflection.transcript_text(self._transcripts,day))
                    summary,loops=reflection.parse_reflection(reply)
                    path=reflection.write_note(self._vault.path,day,summary,loops)
                    logger.info('Daily reflection written: %s (%d open loop(s))',path.name,len(loops))
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning('Daily reflection postponed: %s',exc)
            await asyncio.sleep(1800)

    def _personal_scope(self):
        return self._session_context.context_for_request(self._memory).scope=='personal'

    def _save_session(self):
        """Write the owner's conversation to disk; guests' conversations are never saved."""
        messages=self._hermes.session_messages() if hasattr(self._hermes,'session_messages') else None
        if not isinstance(messages,list) or not messages or not self._personal_scope(): return
        if self._hermes.session_id is None: self._hermes.session_id=new_session_id()
        try: self._sessions.save(self._hermes.session_id,messages,skip_title=lambda text:INITIATIVE_PREFIX in text)
        except (OSError,ValueError) as exc: logger.warning('Chat session not saved: %s',type(exc).__name__)

    def _open_session(self,session_id):
        data=self._sessions.load(session_id)
        self._summarize_later(getattr(self._hermes,'session_id',None))
        self._hermes.load_session(data['id'],data['messages'])
        self._pending_topic=None;self._stream_view=None

    def _resume_latest_session(self):
        """Reopening Chassie continues the last conversation instead of starting blank."""
        if not self._personal_scope(): return
        latest=self._sessions.latest()
        if latest is None or not hasattr(self._hermes,'load_session'): return
        try:
            self._open_session(latest)
            logger.info('Continued chat session %s',latest)
            for item in [s for s in self._sessions.list(20) if s['id']!=latest and s.get('needs_summary')][:3]:
                self._summarize_later(item['id'])
        except (OSError,ValueError) as exc: logger.warning('Could not continue the last chat: %s',type(exc).__name__)

    SUMMARY_SYSTEM=('Summarize this chat between Artdi and his companion Chassie in Indonesian, in one or two '
                    'short sentences: what they talked about and anything left open. Refer to them by name in '
                    'the third person. Plain text only.')

    def _summarize_later(self,session_id):
        """Recap a session the owner just left, in the background; the next chat can recall it."""
        if not isinstance(session_id,str) or not self._personal_scope(): return
        task=asyncio.create_task(self._summarize(session_id))
        self._summary_tasks.add(task);task.add_done_callback(self._summary_tasks.discard)

    async def _summarize(self,session_id):
        try:
            data=self._sessions.load(session_id)
            messages=[m for m in data['messages'] if not (m['role']=='user' and INITIATIVE_PREFIX in m['content'])]
            if len(messages)<4 or data.get('summary_count')==len(data['messages']): return
            lines=[('Artdi: ' if m['role']=='user' else 'Chassie: ')
                   +(display_translation(m['content']) if m['role']=='assistant' else m['content'])[:600] for m in messages[-60:]]
            summary=await self._hermes.complete_once(self.SUMMARY_SYSTEM,'\n'.join(lines))
            self._sessions.set_summary(session_id,summary,len(data['messages']))
            logger.info('Chat session %s summarized',session_id)
            await self._broadcast_to_ui(self._sessions_message())
        except asyncio.CancelledError: raise
        except Exception as exc: logger.warning('Chat summary postponed: %s',type(exc).__name__)

    def _previous_chat(self):
        """Recap of the latest other session, for a fresh or short conversation."""
        current=getattr(self._hermes,'session_id',None)
        messages=self._hermes.session_messages() if hasattr(self._hermes,'session_messages') else []
        if isinstance(messages,list) and len(messages)>=6: return None
        earlier=next((s for s in self._sessions.list(10) if s['id']!=current and s.get('summary')),None)
        return {'summary':earlier['summary'],'when':earlier['updated'][:16]} if earlier else None

    def _sessions_message(self):
        items=self._sessions.list() if self._personal_scope() else []
        current=getattr(self._hermes,'session_id',None)
        return {'type':'sessions','items':items,'current':current if isinstance(current,str) else None,
                'available':self._personal_scope(),
                'reminders':self._reminders.list() if self._personal_scope() else []}

    async def _save_turn_memories(self,text):
        """Save the memory lines Chassie chose to write this turn to the Obsidian vault.

        Owner-only: scope is re-checked after the reply, so a guest who arrived mid-turn blocks it.
        """
        memories=getattr(self,'_turn_memories',[]);self._turn_memories=[]
        if not (memories and self._automatic_memory and self._vault): return
        if self._session_context.context_for_request(self._memory).scope!='personal': return
        saved=0
        for content,extras in memories[:3]:
            try:
                # Title and category shape the Obsidian note; the plugin guesses them when absent.
                result=await asyncio.to_thread(self._vault.call,'remember',content,session='chassie',
                                               title=extras.get('title'),category=extras.get('category'))
                saved+=bool(result.get('saved'))
            except (ValueError,AttributeError) as exc:
                logger.warning('Memory not saved: %s',exc)
        if saved: logger.info('Saved %d memory note(s) to the vault',saved)

    def _apply_face_command(self,action,name):
        if not name:
            # "ingat wajahku" without a name enrolls the owner selected in this trusted local UI,
            # and only when exactly one face is in view, so a bystander is never saved as owner.
            owner=self._session_context.owner_profile_id
            profile=next((p for p in self._memory.list_profiles() if p.id==owner),None)
            if profile is None:
                raise ValueError('Select your owner profile in Settings first, or say the name, e.g. "ingat wajahku sebagai Artdi".')
            if self._vision and self._vision.status().get('identity',{}).get('face_count')!=1:
                raise ValueError('Face not saved. Make sure only your face is in front of the camera, then repeat.')
            name=profile.name
        profiles=[p for p in self._memory.list_profiles() if p.name.casefold()==name.casefold()]
        if len(profiles)>1:
            raise ValueError('Multiple profiles share that name. Remove duplicate profiles in settings first.')
        if action=='forget':
            if profiles and self._memory.delete_face(profiles[0].id):
                return f'Face template for {name} deleted locally. The profile and text memories remain.'
            return f'No saved face template found for {name}.'
        if not self._vision:
            raise ValueError('Camera recognition is unavailable. Enable vision in config and restart Chassie.')
        embedding=self._vision.enrollment()
        profile=profiles[0] if profiles else self._memory.create_profile(name,consent=True)
        self._memory.save_face(profile.id,embedding,consent=True)
        return f'Face remembered locally as {profile.name}. Only a face template was saved, not a camera photo.'

    async def _cancel_turn(self,*,clear=False,keep_voice=False):
        self._generation+=1
        self._subtitle=None
        await self._broadcast_to_ui({'type':'subtitle','text':'','generation':self._generation})
        task=self._turn_task;self._turn_task=None
        if task:
            task.cancel()
        await asyncio.to_thread(self._audio_player.cancel_utterance)
        await self._audio_player.flush_effects()
        if task:
            try: await task
            except asyncio.CancelledError: pass
        self._hermes.interrupt_response(self._spoken)
        self._save_session()  # Keep what was said before a new chat or a guest clears the window.
        if clear:
            self._summarize_later(getattr(self._hermes,'session_id',None))
            self._hermes.clear_history();self._pending_topic=None
            self._stream_view=None
        elif self._stream_view and self._stream_view['interrupted']:
            await self._broadcast_stream()
        if not keep_voice:
            self._purge_inputs()
            self._stt.invalidate()
            await self._broadcast_to_ui({'type':'voice_draft_cleared'})
        self._avatar_state={'emotion':'neutral','mouth':0.0}
        self._capture_paused=False
        await self._sync_capture()
        await self._set_status('idle' if not self._mic_enabled else 'listening')
        await self._broadcast_avatar()

    async def _sync_capture(self):
        # asyncio cancellation cannot stop a native device operation. Keep all
        # capture mutations ordered until the worker has actually completed;
        # otherwise an old mute/unmute could overwrite a newer user decision.
        if not hasattr(self,'_capture_sync_lock'):
            self._capture_sync_lock=asyncio.Lock()
        async with self._capture_sync_lock:
            muted=not self._mic_enabled or self._capture_paused
            pending=asyncio.create_task(asyncio.to_thread(self._stt.set_muted,muted))
            try:
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                # A second Stop/shutdown cancellation must not release the lock
                # while the same native worker is still able to change state.
                while not pending.done():
                    try: await asyncio.shield(pending)
                    except asyncio.CancelledError: pass
                    except Exception: break
                if not pending.cancelled(): pending.exception()
                raise

    async def _handle_speech_event(self,event):
        if event.epoch!=self._stt.epoch or not self._mic_enabled or self._capture_paused: return
        if (event.kind=='speech_start' and self._barge_in and self._current_status=='speaking'
                and time.monotonic()-self._speaking_since>=.6):
            # The grace period ignores residual echo while the canceller adapts to a new reply.
            logger.info('Barge-in: user started speaking; stopping the reply')
            await self._cancel_turn(keep_voice=True)
            return
        if event.kind=='speech_pause':
            # Nod along while the owner talks, at most every 1.6 s; never over Chassie's own speech.
            now=time.monotonic()
            if self._current_status=='listening' and now-self._last_backchannel>=1.6:
                self._last_backchannel=now
                await self._broadcast_to_ui({'type':'backchannel'})
            return
        if event.kind=='speech_start':
            self._note_activity(user=True)
            if self._current_status in ('idle','listening'):
                self._listening_until=time.monotonic()+18
                await self._set_status('listening')
            return
        if event.kind!='transcript': return
        if self._current_status=='listening':await self._set_status('idle')
        speaker=getattr(event,'speaker',None)
        if speaker and 'enrollment' in speaker:
            await self._broadcast_to_ui({'type':'notice','text':speaker['enrollment']})
            await self._broadcast_settings()
            return
        if self._automatic_memory and speaker is not None:
            match=speaker.get('match')
            owner=self._session_context.owner_profile_id
            if self._guest_privacy and (not match or match.get('profile_id')!=owner):
                async with self._control_lock:
                    await self._pause_personal('voice-presence','Speaker is not recognized as you')
            await self._broadcast_to_ui({'type':'speaker_status','name':match.get('name') if match else None})
        if self._input_mode=='review':
            await self._broadcast_to_ui({'type':'stt_transcription','text':event.text})
        else:
            try: self._ui_input_queue.put_nowait({'text':event.text,'source':'voice','epoch':self._stt.epoch})
            except asyncio.QueueFull: await self._broadcast_to_ui({'type':'notice','text':'Input queue is full. Please wait or press Stop.'})

    async def _stt_poll_loop(self):
        pending=False
        while self._running:
            enrolling=bool(self._speaker and self._speaker.enrolling)
            if enrolling!=pending:
                pending=enrolling
                await self._broadcast_settings()
            if self._current_status=='listening' and time.monotonic()>self._listening_until:await self._set_status('idle')
            try: event=self._stt_queue.get_nowait()
            except queue.Empty: await asyncio.sleep(.02);continue
            await self._handle_speech_event(event)










    async def _set_status(self,status):
        self._current_status=status
        await self._broadcast_to_ui({'type':'status','status':status})
        await self._broadcast_avatar()











    async def stop(self):
        self._running=False
        if self._speaker:self._speaker.cancel()
        for task in self._tasks: task.cancel()
        await self._cancel_turn()
        await asyncio.gather(*self._tasks,return_exceptions=True)
        await asyncio.to_thread(self._stt.stop)
        if self._face_tracker: await asyncio.to_thread(self._face_tracker.stop)
        if self._vision and self._vision is not self._face_tracker:
            await asyncio.to_thread(self._vision.stop)
        await asyncio.to_thread(self._audio_player.stop)
        await self._hermes.close()
        if isinstance(self._tts,TTSEngine): await self._tts.close()
        if self._web_runner: await self._web_runner.cleanup()
        self._memory.close()
