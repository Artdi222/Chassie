"""Async conversation control with cancellable turns and explicit local session scope."""
from __future__ import annotations

import re
import asyncio
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
from voice_identity import VoiceIdentity
from hermes_bridge import HermesBridge
from stt_engine import STTEngine
from tts_engine import TTSEngine
from speech_chunker import SpeechChunker
from speech_pacing import SpeechPacing
from bilingual import BilingualChunker, LANGUAGES, split_first_clause
from vts_connector import VTSConnector
from avatar import load_manifest
from avatar.manifest import DEFAULT_MANIFEST
from avatar.catalog import ModelCatalog, ModelSelection
from face_identity import face_command
from visual_context import VisualContext
from visual_requests import requested_visual_sources
from app_context import active_application

logger=logging.getLogger('orchestrator')

from chassie_core.controls import ControlsMixin
from chassie_core.presence import PresenceMixin
from chassie_core.web import WebMixin

class _AvatarOutput:
    def __init__(self, owner): self.owner=owner
    async def trigger_emotion(self,emotion):
        self.owner._avatar_state['emotion']=emotion
        await self.owner._broadcast_avatar()
        return await self.owner._vts.trigger_emotion(emotion)
    async def set_mouth_open(self,value):
        value=float(value)
        self.owner._avatar_state['mouth']=value
        await self.owner._broadcast_avatar()
        await self.owner._vts.set_mouth_open(value)

class Orchestrator(ControlsMixin,WebMixin,PresenceMixin):
    def __init__(self,config,text_mode=False,*,components=None):
        c=components or {}
        self._config=config
        self._bilingual=config.get('tts',{}).get('engine')=='voicevox'; self._text_mode=text_mode; self._running=False
        self._stt_queue=queue.Queue(maxsize=32)
        self._stt=c.get('stt') or STTEngine(config,self._stt_queue)
        self._hermes=c.get('hermes') or HermesBridge(config)
        self._tts=c.get('tts') or TTSEngine(config)
        self._vts=c.get('vts') or VTSConnector(config)
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
        self._face_command_result=None
        self._session_context=SessionContext()
        self._automatic_memory=config.get('companion',{}).get('automatic_memory',False) is True
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
        self._avatar_manifest=load_manifest(config.get('vts',{}).get('expression_manifest',DEFAULT_MANIFEST))
        self._ui_input_queue=asyncio.Queue(maxsize=16)
        self._current_status='idle';self._turn_task=None;self._tasks=[]
        self._listening_until=0.
        self._generation=0;self._spoken='';self._pending_topic=None
        self._stream_view=None
        self._turn_metrics={}
        self._mic_enabled=not text_mode
        self._voice_started=False;self._voice_starting=False;self._voice_start_task=None
        self._capture_paused=False
        # Full duplex only when echo_cancel.enable() routed audio through PipeWire AEC.
        self._barge_in=config.get('conversation',{}).get('barge_in') is True
        self._speaking_since=0.0
        self._input_mode=config.get('conversation',{}).get('input_mode','review')
        if self._input_mode not in ('review','hands_free'): raise ValueError('Invalid input mode')
        self._speech_settings_path=selection_path.with_name('speech-settings.json')
        self._translation_language=config.get('tts',{}).get('translation_language','en')
        try:self._translation_language=json.loads(self._speech_settings_path.read_text())['translation_language']
        except (OSError,ValueError,KeyError,TypeError):pass
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
        self._tts.load_model()
        self._audio_player.start(loop=asyncio.get_running_loop(),vts=self._avatar,analyzer=self._audio_analyzer)
        # Start web controls before expensive device/model loading.
        self._web_runner=web.AppRunner(self._web_app);await self._web_runner.setup()
        cfg=self._config.get('ui',{})
        await web.TCPSite(self._web_runner,'127.0.0.1',cfg.get('port',8000)).start()
        if isinstance(self._tts,TTSEngine):self._tts.start()
        self._tasks=[asyncio.create_task(self._vts_reconnect_loop()),asyncio.create_task(self._stt_poll_loop()),asyncio.create_task(self._face_monitor_loop())]
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

    def _context_text(self):
        context=self._session_context.context_for_request(self._memory)
        payload={'scope':context.scope,'mode':context.mode,
                 'memories':[] if self._automatic_memory else [{'content':m.content,'source':m.source} for m in context.memories[-8:]],
                 'shared_notes':list(context.shared_notes[-4:])}
        if context.scope=='personal':
            payload['profile_id']=self._session_context.owner_profile_id
        if self._speaker and self._speaker.last and time.monotonic()-self._speaker.last['at']<30:
            match=self._speaker.last.get('match')
            payload['speaker_observation']={'name':match['name'] if match else None,
                'note':'Recent local voice similarity hint, not verified identity. Do not infer or save personal facts about this person from this hint.'}
        if self._turn_vision is not None:
            payload['vision']=dict(self._turn_vision)
            payload['vision']['note']='Availability describes current snapshots only. Face matches are visual hints, not speaker identity or authentication.'
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
        return chunks

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
        async def put(sentence):
            nonlocal first_pair
            self._turn_metrics.setdefault('first_sentence_seconds',time.monotonic()-started)
            parts=split_first_clause(sentence[2]) if self._bilingual and first_pair else [None]
            first_pair=False
            if len(parts)==1: await sentences.put(sentence);return
            # Only the reply's first sentence waits on synthesis; later ones are prefetched during playback.
            emotion,translation=sentence[:2]
            await sentences.put((emotion,translation,parts[0],'head'))
            await sentences.put((emotion,translation,parts[1],'tail'))
        received_length=0
        stream=self._hermes.stream_message(text,context=self._context_text(),mode=self._session_context.mode,
                                          **({'images':self._turn_images} if self._turn_images else {}))
        try:
            async for delta in stream:
                if generation!=self._generation: return
                self._turn_metrics.setdefault('first_text_seconds',time.monotonic()-started)
                received_length+=len(delta)
                if received_length>30000: raise RuntimeError('Response too long')
                for sentence in chunker.feed(delta):
                    if sentence[0]=='action':
                        await self._run_model_action(text,*sentence[1:]);continue
                    await put(sentence)
            self._turn_metrics['hermes_complete_seconds']=time.monotonic()-started
            for sentence in chunker.finish():
                if sentence[0]=='action':
                    await self._run_model_action(text,*sentence[1:]);continue
                await put(sentence)
            await sentences.put(None)
        except (ValueError, RecursionError) as exc:
            if not self._bilingual: raise
            raise RuntimeError(f'The reply did not contain valid Japanese speech and {LANGUAGES[self._translation_language]} translations. Please retry.') from exc
        finally:
            await stream.aclose()

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
                    if first: raise RuntimeError('Hermes returned no speakable text.')
                    break
                emotion,sentence,chunks,part,speech=item
                if generation!=self._generation: return
                delay=pacing.delay(chunks,now=time.monotonic())
                if delay:
                    await asyncio.sleep(delay)
                    if generation!=self._generation: return
                chunks=pacing.smooth(chunks)
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
                for chunk_index,pcm in enumerate(chunks):
                    if generation!=self._generation: return
                    if not await self._audio_player.enqueue(pcm,emotion=emotion,generation=job):
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
        self._pending_topic=text
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
                requested=requested_visual_sources(text)
                if requested:
                    frames,status=self._vision.request_context()
                    self._turn_images=[frame for frame in frames if frame['source'] in requested]
                    self._turn_vision={source:status.get(source,{}) for source in requested}
                    if 'camera' in requested:
                        self._turn_vision['identity']=status.get('identity',{})
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
            await self._broadcast_to_ui({'type':'chat','role':'user','text':text})
            await self._set_status('thinking')
            command=face_command(text)
            if command:
                self._face_command_result=self._apply_face_command(*command)
                if self._turn_vision:
                    self._turn_vision={**self._turn_vision,'identity':{**self._turn_vision.get('identity',{}),'matches':[]}}
                await self._broadcast_to_ui({'type':'notice','scope':'chat','text':self._face_command_result})
            sentences=asyncio.Queue(maxsize=8)
            tasks=[asyncio.create_task(self._produce_speech(text,generation,sentences,started)),
                   asyncio.create_task(self._play_speech(sentences,generation,started))]
            await asyncio.gather(*tasks)
            if generation!=self._generation: return
            self._hermes.complete_response()
            self._pending_topic=None
            completed=True
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
            logger.warning('Reply failed after %.3fs: %s; timings=%s',time.monotonic()-started,
                           type(exc).__name__,{k:round(v,3) for k,v in self._turn_metrics.items()})
            await self._broadcast_to_ui({'type':'notice','scope':'chat',
                                        'stream_id':self._stream_view['id'],'text':str(exc)[:250],'retry_text':text})
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            self._turn_images=[]
            self._turn_vision=None
            self._turn_app=None
            self._face_command_result=None
            self._stream_view['done']=True
            self._stream_view['interrupted']=not completed
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

    def _purge_inputs(self,voice_only=False):
        keep=[]
        while not self._ui_input_queue.empty():
            item=self._ui_input_queue.get_nowait()
            if voice_only and item.get('source')!='voice': keep.append(item)
        for item in keep: self._ui_input_queue.put_nowait(item)

    async def _run_model_action(self,user_text,action,name):
        """Run a model-requested action before any speech; a failure stops the reply."""
        if self._face_command_result is not None:
            return  # The local command parser already handled this message.
        # Privacy guard: never enroll or delete a face unless the user's own message is about faces.
        if not re.search(r'\b(?:wajah\w*|muka\w*|faces?)\b',user_text,re.IGNORECASE):
            logger.warning('Ignored model action %s without a face request',action)
            return
        try:self._face_command_result=self._apply_face_command('remember' if action=='remember_face' else 'forget',name)
        except ValueError as exc:raise RuntimeError(str(exc)) from exc  # Keep the real reason visible.
        await self._broadcast_to_ui({'type':'notice','scope':'chat','text':self._face_command_result})

    def _apply_face_command(self,action,name):
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
        if clear:
            self._hermes.clear_history();self._pending_topic=None
            self._stream_view=None
        elif self._stream_view and self._stream_view['interrupted']:
            await self._broadcast_stream()
        if not keep_voice:
            self._purge_inputs()
            self._stt.invalidate()
            await self._broadcast_to_ui({'type':'voice_draft_cleared'})
        self._avatar_state={'emotion':'neutral','mouth':0.0}
        await self._vts.reset_expressions()
        await self._vts.set_mouth_open(0)
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
        if event.kind=='speech_start':
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
            if not match or match.get('profile_id')!=owner:
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
        await self._vts.disconnect();await self._hermes.close()
        if isinstance(self._tts,TTSEngine): await self._tts.close()
        if self._web_runner: await self._web_runner.cleanup()
        self._memory.close()
