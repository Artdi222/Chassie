"""Web/WebSocket transport, overlay readiness and avatar broadcasts."""
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import web
from brain.initiative import PREFIX as INITIATIVE_PREFIX

logger=logging.getLogger('orchestrator')


class WebMixin:
    async def _handle_ui_websocket(self,request):
        origin=request.headers.get('Origin')
        try: host=urlsplit('//'+request.host).hostname
        except ValueError: host=None
        if host not in ('127.0.0.1','localhost','::1'): raise web.HTTPForbidden(text='Loopback host required')
        if origin and (urlsplit(origin).scheme not in ('http','https') or urlsplit(origin).netloc!=request.host): raise web.HTTPForbidden(text='Local origin required')
        ws=web.WebSocketResponse(max_msg_size=16384,heartbeat=30)
        await ws.prepare(request)
        try:
            # Hydrate before live delivery, while excluding concurrent guest/clear controls.
            # Bound the send so an unresponsive local client cannot hold the control lock.
            async with self._control_lock:
                async with asyncio.timeout(2):
                    await ws.send_json(self._settings())
                    await ws.send_json({'type':'model_catalog',**self._catalog.public()})
                    await ws.send_json(self._model_selection.payload())
                    if self._subtitle: await ws.send_json(self._subtitle)
                    await ws.send_json({'type':'status','status':self._current_status})
                    await ws.send_json(self._avatar_payload())
                    await ws.send_json({'type':'avatar_inventory','capabilities':self._avatar_capabilities()})
                    active_stream_id=self._stream_view['id'] if self._stream_view and not self._stream_view['done'] else None
                    await ws.send_json(self._history_snapshot())
                    await ws.send_json(self._sessions_message())
                    if self._automatic_memory and self._vault and getattr(self._vault,'store',True) is None:
                        await ws.send_json({'type':'notice','text':'Memory is off: '+str(self._vault.error)})
                    self._ui_sockets.add(ws)
                    if self._stream_view and self._stream_view['id']==active_stream_id and self._stream_view['text']:
                        await ws.send_json({'type':'chat_stream',**{k:v for k,v in self._stream_view.items() if k!='user_text'}})
            async for msg in ws:
                if msg.type==web.WSMsgType.TEXT:
                    try:
                        data=json.loads(msg.data)
                        if isinstance(data,dict) and data.get('type')=='overlay_ready':
                            await self._register_overlay(ws,data)
                            continue
                        result=await self.handle_control(data)
                        if result: await ws.send_json(result)
                    except (ValueError,KeyError,TypeError,asyncio.QueueFull) as exc:
                        await ws.send_json({'type':'notice','text':str(exc)[:250]})
        finally:
            self._ui_sockets.discard(ws)
            if self._overlay_sockets.pop(ws,None) is not None:
                await self._broadcast_avatar_inventory()
        return ws

    def _history_snapshot(self):
        items=[{'role':m['role'],'text':m['content']} for m in self._hermes.get_history()
               if m['role'] in ('user','assistant')]
        view=self._stream_view
        if view and not view['done']:
            if (len(items)>=2 and items[-1]['role']=='assistant'
                    and items[-2]=={'role':'user','text':view['user_text']}):
                items[-1]['text']=view['text']
                items[-1]['stream_id']=view['id']
                if not view['text']: items.pop()
            else:
                items.append({'role':'user','text':view['user_text']})
                if view['text']: items.append({'role':'assistant','text':view['text'],'stream_id':view['id']})
        # Initiative prompts are Chassie's own cues, never shown as user messages.
        items=[i for i in items if not (i['role']=='user' and INITIATIVE_PREFIX in str(i['text']))]
        return {'type':'history_snapshot','items':items}

    async def _register_overlay(self,ws,data):
        if ws not in self._ui_sockets or type(data.get('ready')) is not bool:
            raise ValueError('Renderer readiness requires a live WebSocket and a boolean ready value')
        # Re-registration first revokes prior readiness, including a failed reload.
        self._overlay_sockets.pop(ws,None)
        try:
            if data['ready']:
                model_id=data.get('model_id')
                selected=self._model_selection.state['model_id']
                if model_id!=selected:
                    raise ValueError('Overlay model does not match the selected model')
                files=data.get('expressions')
                if not isinstance(files,list) or len(files)>256 or any(not isinstance(f,str) for f in files):
                    raise ValueError('Overlay must report its loaded expression filenames')
                # Catalog models react through generated parameters, not expression files.
                self._overlay_sockets[ws]=frozenset()
        finally:
            await self._broadcast_avatar_inventory()

    def _avatar_capabilities(self):
        overlays=[files for ws,files in self._overlay_sockets.items()
                  if ws in self._ui_sockets and not ws.closed]
        emotions={}
        for name,mapping in self._avatar_manifest.emotions.items():
            backends=[]
            if any(set(mapping.files)<=files for files in overlays): backends.append('overlay')
            emotions[name]={'files':list(mapping.files),'note':mapping.note,
                            'preview_required':mapping.preview_required,
                            'available':bool(backends),'backends':backends}
        return {'model_id':self._avatar_manifest.model_id,'overlay_ready':bool(overlays),'emotions':emotions}

    async def _broadcast_avatar_inventory(self):
        await self._broadcast_to_ui({'type':'avatar_inventory','capabilities':self._avatar_capabilities()})

    async def _broadcast_to_ui(self,message):
        async def send(ws):
            try: await asyncio.wait_for(ws.send_json(message),timeout=.5)
            except (ConnectionError,RuntimeError,asyncio.TimeoutError): self._ui_sockets.discard(ws)
        if self._ui_sockets: await asyncio.gather(*(send(ws) for ws in tuple(self._ui_sockets)))

    def _avatar_payload(self):
        gaze=self._vision.gaze() if self._vision and hasattr(self._vision,'gaze') else None
        valid=isinstance(gaze,tuple) and len(gaze)==2 and all(type(v) is float for v in gaze)
        return {'type':'avatar_state',**self._avatar_state,'generation':self._generation,'status':self._current_status,
                'gaze':list(gaze) if valid else None}

    async def _broadcast_avatar(self): await self._broadcast_to_ui(self._avatar_payload())

    async def _handle_index(self,request): return web.FileResponse(Path(__file__).resolve().parents[1]/'ui/index.html')

    async def _handle_status(self,request): return web.json_response({'application':'chassie','protocol':2,'status':self._current_status,'voice_ready':self._stt.is_listening(),'automatic_barge_in':self._barge_in})

    async def _handle_models(self,request):
        return web.json_response(self._catalog.public())

    async def _handle_model_manifest(self,request):
        try: return web.json_response(self._catalog.web_manifest(request.match_info['model_id']))
        except ValueError: raise web.HTTPNotFound()

    async def _handle_model_asset(self,request):
        try:
            entry=self._catalog.get(request.match_info['model_id'])
            generated=entry.generated.get(request.match_info['asset'])
            if generated is not None:return web.json_response(generated)
            path=entry.assets.get(request.match_info['asset'])
            if path is None or not path.resolve().is_relative_to(entry.root): raise ValueError('Unknown asset')
            return web.FileResponse(path)
        except ValueError: raise web.HTTPNotFound()
