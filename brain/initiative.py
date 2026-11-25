"""Chassie speaks first: quiet check-ins, greetings, reactions to the camera, and look-again.

Every initiative becomes an ordinary turn whose message starts with [Chassie initiative];
the model may answer {"skip":true} to stay silent. Initiatives run only for the owner alone
(personal scope), never during a reply, and are rate limited.
"""
from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass, field
import datetime
import logging
import time

from vision.app_context import active_application

logger=logging.getLogger('orchestrator')

PREFIX='[Chassie initiative] '
# quiet: seconds of silence before a check-in; cooldown: between any two initiatives.
MODES={'normal':{'quiet':60,'cooldown':180,'per_hour':8},
       'rare':{'quiet':240,'cooldown':600,'per_hour':3},
       'off':None}
AWAY_SECONDS=180      # Owner must be out of view this long before a welcome-back.
APP_STABLE_SECONDS=90 # A new app must stay focused this long before Chassie mentions it.
OPEN_DELAY=6.0       # Seconds after opening before her hello (the avatar and voice are ready).
LOOK_DELAY=4.0        # After "bring it closer", give the user time to do it.
MAX_LOOK_CHAIN=2


@dataclass
class InitiativeState:
    mode:str='normal'
    last_activity:float=0.0
    last_initiative:float=-1e9
    unanswered:int=0
    history:deque=field(default_factory=lambda:deque(maxlen=16))
    away_since:float|None=None
    present_since:float|None=None
    pending_return:bool=False
    app:str|None=None
    app_since:float=0.0
    app_mentioned:str|None=None
    look:dict|None=None
    look_chain:int=0
    late_night_day:str|None=None
    greeted:bool=True   # False right after Chassie opens: she says hello first, once.
    opened_at:float=0.0
    events:list=field(default_factory=list)
    last_face_seen:float|None=None
    last_wait_log:float=-1e9
    pending_signal:tuple|None=None  # (reason, time) of the last spoken initiative, until answered


def decide(state,now,*,owner_alone,face_visible,camera_on,mic_on,clock_time,screen_on=False,
           agenda_item=None,acceptance=None):
    """Return (reason, detail, sources) for the next initiative, or None.

    Pure: callers pass observations; only `state` fields are read here. `acceptance(reason)`
    is how often the owner answered that kind of initiative at this hour (0.5 = unknown):
    well-received ones come sooner, ignored ones later, within half to four times the wait.
    """
    def wait(reason,base):
        share=acceptance(reason) if acceptance else .5
        return base*min(4.,max(.5,.5/max(share,1e-6)))
    settings=MODES.get(state.mode)
    if not owner_alone:return None
    if state.look and state.look['due'] is not None and now>=state.look['due']:
        return 'look',state.look['source'],{state.look['source']}
    # A muted mic only means the owner types; it is not a request for silence (use mode 'off').
    if settings is None:return None
    if not state.greeted:
        if camera_on and not face_visible:return None  # Greet once they sit down.
        if now-state.opened_at>=OPEN_DELAY:return 'opened',None,set()
        return None
    if now-state.last_initiative<settings['cooldown']:return None
    if sum(1 for t in state.history if now-t<3600)>=settings['per_hour']:return None
    quiet=now-state.last_activity
    if camera_on and not face_visible:return None  # Nobody to talk to.
    if state.pending_return:return 'returned',None,{'camera'}
    screen={'screen'} if screen_on else set()
    if screen_on and any(label=='screen_changed' for _,label in state.events) and quiet>=20:
        return 'screen',None,{'screen'}
    camera_events=[label for _,label in state.events if label!='screen_changed']
    if camera_events and quiet>=20:
        return 'noticed',', '.join(camera_events),{'camera'}
    if 0<=clock_time.hour<4 and state.late_night_day!=clock_time.date().isoformat() and quiet>=60:
        return 'late_night',clock_time.strftime('%H:%M'),set()
    if (state.app and state.app!=state.app_mentioned and now-state.app_since>=APP_STABLE_SECONDS
            and quiet>=wait('app',45)):
        return 'app',state.app,set(screen)
    # Something on her mind comes up sooner than a plain check-in.
    if agenda_item and quiet>=wait('agenda',settings['quiet'])/2:
        return 'agenda',agenda_item,set(screen)
    # Back off while check-ins go unanswered so an empty room is not talked to.
    if quiet>=wait('quiet',settings['quiet'])*(2**min(state.unanswered,3)):
        return 'quiet',int(quiet//60),set(screen)
    return None


def initiative_text(reason,detail,now_local):
    clock=now_local.strftime('%H:%M')
    if reason=='agenda':
        return (f'{PREFIX}Local time {clock}. Something on your mind to bring up: "{detail["text"]}" '
                f'({detail["kind"]}). Bring it up naturally in your own words, as a question or a short '
                'remark; skip if it no longer fits.')
    texts={
        'look':f'Fresh {detail} snapshot you asked to see is attached. React to what you see now.',
        'returned':'The owner just came back in front of the camera after being away for a while. '
                   'A camera snapshot is attached. Greet them back naturally, maybe notice something.',
        'noticed':f'The camera view just changed (local hint: {detail}; the hint may be wrong). '
                  'A camera snapshot is attached. If something new or interesting is visible, '
                  'react or ask about it like a friend in the room would; otherwise skip.',
        'screen':'What is on the owner\'s screen just changed a lot (a new app, game, video or page). '
                 'A screen snapshot is attached. If it is interesting, comment or ask about it like a '
                 'friend watching along would (a game, a video, what they are working on); otherwise skip.',
        'late_night':f'It is {detail} at night and the owner is still up. Check on them gently if it fits.',
        'app':f'The owner has been using {detail} for a while (a screen snapshot is attached when '
              'available). Say something about what they are doing only if natural.',
        'opened':'Chassie was just opened on the owner\'s computer. Say hello first, like a friend who '
                 'notices they are here: fit it to the time of day, or pick up something from previous_chat '
                 'or memories (a plan, how something went). One or two short sentences; do not skip.',
        'reminder':f'Reminder the owner asked you to give now: "{detail}". Say it now, briefly and '
                   'warmly, in your own words; do not skip.',
        'quiet':f'The owner has been quiet for about {detail} minutes. Start a short, natural chat if '
                'you like: follow up on something from memories (a plan, an event, how something '
                'went), react to the current app, or just check in. Skip if nothing fits.',
    }
    return f'{PREFIX}Local time {clock}. {texts[reason]}'


class InitiativeMixin:
    def _init_initiative(self,saved_mode=None):
        mode=saved_mode or self._config.get('initiative',{}).get('mode','normal')
        now=time.monotonic()
        self._initiative=InitiativeState(mode=mode if mode in MODES else 'normal',last_activity=now,
                                         greeted=False,opened_at=now)

    def _note_activity(self,*,user=False):
        state=self._initiative
        state.last_activity=time.monotonic()
        if state.look and state.look['due'] is None and not user:
            # The delay starts when Chassie finishes speaking, giving the user time to act.
            state.look['due']=state.last_activity+LOOK_DELAY
        if user and state.pending_signal:
            reason,since=state.pending_signal;state.pending_signal=None
            if state.last_activity-since<=600:self._signals.add('answered',reason)  # They answered her.
        if user:
            state.greeted=True  # They spoke first; no opening hello now.
            state.unanswered=0
            state.look=None;state.look_chain=0

    def _request_look(self,source):
        state=self._initiative
        if state.look_chain>=MAX_LOOK_CHAIN:
            logger.info('Ignored look request: chain limit reached');return
        if not (self._vision and getattr(self._vision,source+'_enabled',False)):return
        state.look={'source':source,'due':None}

    def _owner_alone(self):
        return self._session_context.context_for_request(self._memory).scope=='personal'

    def _track_presence(self,now):
        """Return whether the owner is around: away only after being seen and then missing.

        Face detection misses frames (light, angle), so one empty frame never means away.
        """
        state=self._initiative
        if not (self._vision and self._vision.camera_enabled):return False
        status=self._vision.status()
        visible=status['camera']['available'] and status['identity'].get('face_count',0)>=1
        if visible:state.last_face_seen=now
        if visible:
            state.present_since=state.present_since or now
            if state.away_since is not None and state.away_since<=now-AWAY_SECONDS and now-state.present_since>=3:
                state.pending_return=True;state.away_since=None
            elif state.away_since is not None and now-state.present_since>=3:
                state.away_since=None  # Short absence: not a return.
        else:
            state.present_since=None
            if state.away_since is None:state.away_since=now
            state.pending_return=False
        state.events.extend(self._vision.pop_events())
        state.events=[e for e in state.events if now-e[0]<=30][-4:]
        return state.last_face_seen is None or now-state.last_face_seen<AWAY_SECONDS

    async def _initiative_loop(self):
        app_checked=0.0
        reminders_checked=0.0
        gaze=None
        while self._running:
            await asyncio.sleep(1)
            try:
                now=time.monotonic()
                state=self._initiative
                visible=self._track_presence(now)
                current=self._vision.gaze() if self._vision and hasattr(self._vision,'gaze') else None
                if current!=gaze:
                    gaze=current;await self._broadcast_avatar()  # Avatar eyes follow the owner's face.
                if self._config.get('app_context',{}).get('enabled',False) and now-app_checked>=10:
                    app_checked=now
                    app=(await asyncio.to_thread(active_application)).get('app')
                    if app and app!=state.app:state.app,state.app_since=app,now
                busy=(self._turn_task and not self._turn_task.done()) or not self._ui_input_queue.empty()
                if busy or self._current_status not in ('idle','listening'):continue
                if now-reminders_checked>=10:
                    reminders_checked=now
                    camera_on=bool(self._vision and self._vision.camera_enabled)
                    # Wait until the owner is in front of the camera, so nobody talks to an empty room.
                    due=self._reminders.due() if self._owner_alone() and (visible or not camera_on) else []
                    if due:
                        # Reminders bypass the chatty limits: the owner asked for them.
                        self._reminders.done(due[0]['id'])
                        await self._start_initiative('reminder',due[0]['text'],set())
                        await self._broadcast_to_ui(self._sessions_message())
                        continue
                choice=decide(state,now,owner_alone=self._owner_alone(),face_visible=visible,
                              camera_on=bool(self._vision and self._vision.camera_enabled),
                              mic_on=self._mic_enabled,clock_time=datetime.datetime.now(),
                              screen_on=bool(self._vision and getattr(self._vision,'screen_enabled',False)),
                              agenda_item=self._agenda.best() if self._owner_alone() else None,
                              acceptance=lambda reason:self._signals.acceptance(reason,datetime.datetime.now().hour))
                if choice:await self._start_initiative(*choice)
                else:self._log_wait(now,visible)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning('Initiative check failed: %s',exc)

    def _log_wait(self,now,present):
        """Once per two minutes, say why a long silence is not producing a check-in."""
        state=self._initiative
        settings=MODES.get(state.mode)
        quiet=now-state.last_activity
        if settings is None or quiet<settings['quiet'] or now-state.last_wait_log<120:return
        state.last_wait_log=now
        reasons=[name for name,blocked in (
            ('not personal scope',not self._owner_alone()),
            ('owner away from camera',not present),
            ('cooldown',now-state.last_initiative<settings['cooldown']),
            ('hourly limit',sum(1 for t in state.history if now-t<3600)>=settings['per_hour']),
            ('backing off after unanswered check-ins',quiet<settings['quiet']*(2**min(state.unanswered,3)))) if blocked]
        logger.info('Initiative waiting after %ds quiet: %s',int(quiet),', '.join(reasons) or 'no trigger')

    async def _start_initiative(self,reason,detail,sources):
        state=self._initiative
        now=time.monotonic()
        if reason=='look':
            state.look=None;state.look_chain+=1
        elif reason!='reminder':
            state.look_chain=0
            state.last_initiative=now;state.history.append(now);state.unanswered+=1
        if reason=='returned':state.pending_return=False
        if reason=='opened':state.greeted=True
        if reason=='noticed':state.events=[e for e in state.events if e[1]=='screen_changed']
        if reason=='screen':state.events=[e for e in state.events if e[1]!='screen_changed']
        if reason=='app':state.app_mentioned=detail
        if reason=='late_night':state.late_night_day=datetime.date.today().isoformat()
        logger.info('Initiative: %s',reason)
        async with self._control_lock:
            if (self._turn_task and not self._turn_task.done()) or not self._ui_input_queue.empty():return
            self._ui_input_queue.put_nowait({'text':initiative_text(reason,detail,datetime.datetime.now()),
                                             'source':'initiative','visual':sorted(sources),'reason':reason})
            if reason=='agenda':self._agenda.raised(detail['id'])  # Twice unresolved and it is dropped.

    async def _set_initiative_mode(self,mode):
        if mode not in MODES:raise ValueError('Choose normal, rare or off')
        self._initiative.mode=mode
