"""Camera/voice presence, personal-memory pausing and background monitors."""
from __future__ import annotations
import asyncio
import logging
import time

logger=logging.getLogger('orchestrator')


class PresenceMixin:
    async def _pause_personal(self,identifier,reason):
        if any(g.id==identifier for g in self._session_context.guests):return
        await self._cancel_turn(clear=True)
        self._session_context.mark_guest_present(identifier,reason)
        self._owner_alone_since=None
        await self._broadcast_to_ui({'type':'history_cleared'})
        await self._broadcast_to_ui({'type':'memories','items':[]})
        await self._broadcast_to_ui({'type':'notice','text':reason+'. Personal memory is paused.'})
        await self._broadcast_settings()

    async def _update_presence(self,status,now):
        reason=self._visual_guest_reason(status)
        if reason:
            await self._pause_personal('camera-presence',reason)
            self._owner_alone_since=None
            return
        identity=status.get('identity',{})
        matches=identity.get('matches',[])
        owner_alone=(status.get('camera',{}).get('available') and identity.get('ready')
                     and identity.get('face_count')==1 and len(matches)==1
                     and matches[0].get('profile_id')==self._session_context.owner_profile_id)
        if not self._automatic_memory or not owner_alone:
            self._owner_alone_since=None;return
        if self._owner_alone_since is None:self._owner_alone_since=now
        # Restore only camera-triggered sharing in the already trusted local
        # session. A face match cannot resolve who spoke or switch the owner.
        if now-self._owner_alone_since>=5 and any(g.id=='camera-presence' for g in self._session_context.guests):
            await self._cancel_turn(clear=True)
            self._session_context.remove_guest('camera-presence')
            await self._broadcast_to_ui({'type':'history_cleared'})
            await self._broadcast_settings()

    async def _face_monitor_loop(self):
        previous=None
        while self._running:
            if self._face_tracker or self._vision:
                observation=self._vision.get_observation() if self._vision else self._face_tracker.get_observation()
                async with self._control_lock:
                    if self._vision and self._vision.camera_enabled:await self._update_presence(self._vision.status(),time.monotonic())
                    elif getattr(self,'_guest_privacy',True) and observation['available'] and observation['face_count']>1:await self._pause_personal('camera-presence','Additional face detected')
                state=(observation['available'],observation['face_count'],observation['expression'])
                if state!=previous:
                    previous=state
                    label=(str(observation['face_count'])+' unidentified face(s)') if observation['available'] else 'Camera unavailable / no face'
                    await self._broadcast_to_ui({'type':'face_context','expression':label})
            await asyncio.sleep(.2)

    def _visual_guest_reason(self,status):
        if not getattr(self,'_guest_privacy',True):
            return None  # Owner chose to keep personal context while others are on camera.
        camera=status.get('camera',{})
        identity=status.get('identity',{})
        # A camera that is still warming up (no frame yet, no error) is not a failure;
        # flagging it locked the session in shared scope before the first frame arrived.
        if (self._session_context.owner_profile_id and camera.get('enabled')
                and ((not camera.get('available') and camera.get('error'))
                     or (camera.get('available') and identity.get('presence_ready') is False))):
            return 'Camera presence could not be checked'
        if camera.get('available') and identity.get('face_count',0)>1:
            return 'Additional face detected'
        if self._automatic_memory and camera.get('available') and any(
                p.get('profile_id')!=self._session_context.owner_profile_id for p in identity.get('matches',[])):
            return 'Someone else is present'
        return None

    async def _vision_status_loop(self):
        previous=None
        while self._running:
            status=self._vision.status()
            if status!=previous:
                previous=status
                await self._broadcast_to_ui({'type':'vision_status',**status})
            await asyncio.sleep(1)
