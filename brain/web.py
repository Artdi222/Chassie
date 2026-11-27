"""Web/WebSocket transport, overlay readiness and avatar broadcasts."""
from __future__ import annotations
import asyncio
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from aiohttp import web
from brain.initiative import PREFIX as INITIATIVE_PREFIX
from paths import DATA

logger=logging.getLogger('orchestrator')


def _require_local(request):
    """Only this computer's own pages may drive Chassie (no DNS rebinding, no other sites)."""
    origin=request.headers.get('Origin')
    try: host=urlsplit('//'+request.host).hostname
    except ValueError: host=None
    if host not in ('127.0.0.1','localhost','::1'): raise web.HTTPForbidden(text='Loopback host required')
    if origin and (urlsplit(origin).scheme not in ('http','https') or urlsplit(origin).netloc!=request.host): raise web.HTTPForbidden(text='Local origin required')


class WebMixin:
    async def _handle_ui_websocket(self,request):
        _require_local(request)
        # Local only (checked above). 4 MB: the overlay's one avatar picture (avatar_snapshot, under 3 MB) must
        # fit; at 16 KB it closed the socket, and the reconnect asked for the picture again in a loop.
        ws=web.WebSocketResponse(max_msg_size=4*1024*1024,heartbeat=30)
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
                await self._sync_appearance()  # Her look follows whichever avatar just loaded.
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

    async def _handle_index(self,request):
        if not self._catalog.models and 'panel' not in request.query: raise web.HTTPFound('/onboarding')
        return web.FileResponse(Path(__file__).resolve().parents[1]/'ui/index.html')

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

    # ---- First-run onboarding and model import -------------------------------------------

    def _onboarding_path(self):
        path=getattr(self._model_selection,'path',None)
        return (path.parent if path else DATA/'.chassie')/'onboarding.json'

    def _onboarding_state(self):
        try: done=bool(json.loads(self._onboarding_path().read_text()).get('completed'))
        except (OSError,ValueError,AttributeError): done=False
        return {'completed':done,'has_model':bool(self._catalog.models),
                'model_id':self._model_selection.state['model_id']}

    async def _handle_onboarding_page(self,request):
        return web.FileResponse(Path(__file__).resolve().parents[1]/'ui/onboarding.html')

    async def _handle_onboarding(self,request):
        _require_local(request)
        if request.method=='POST':
            if not self._catalog.models: raise web.HTTPConflict(text='Add a Live2D model first')
            path=self._onboarding_path();path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'completed':True,'at':time.time()}))
        return web.json_response(self._onboarding_state())

    async def _handle_model_import(self,request):
        """Accept one .zip, or the files of a picked folder (filenames carry their relative paths)."""
        from avatar.importer import MAX_BYTES, MAX_FILES, ImportError_, install, _clean
        _require_local(request)
        model_dir=self._catalog.root
        model_dir.mkdir(parents=True,exist_ok=True)
        work=Path(tempfile.mkdtemp(prefix='.upload-',dir=model_dir))
        try:
            reader=await request.multipart()
            total=count=0;archive=None;folder=work/'folder';top=None
            while (part:=await reader.next()) is not None:
                if not part.filename: continue
                count+=1
                if count>MAX_FILES: raise ImportError_(f'Too many files (more than {MAX_FILES}).')
                name=unquote(part.filename).replace('\\','/')  # Some clients percent-encode '/'.
                if name.lower().endswith('.zip') and '/' not in name:
                    if archive or count>1: raise ImportError_('Pick one zip file at a time.')
                    archive=dest=work/'upload.zip';top=PurePosixPath(name).stem
                else:
                    if archive: raise ImportError_('Pick one zip file at a time.')
                    clean=_clean(name)
                    if clean is None: continue
                    top=top or clean.parts[0]
                    dest=folder/clean
                    dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open('wb') as out:
                    while chunk:=await part.read_chunk(1<<20):
                        total+=len(chunk)
                        if total>MAX_BYTES: raise ImportError_('This upload is larger than 1.5 GB.')
                        out.write(chunk)
            if count==0: raise ImportError_('Nothing was uploaded. Pick a .zip file or a model folder.')
            installed=await asyncio.to_thread(install,archive or folder,model_dir,fallback_name=top or 'Model')
        except ImportError_ as exc:
            return web.json_response({'error':str(exc)},status=400)
        finally:
            shutil.rmtree(work,ignore_errors=True)
        async with self._control_lock:
            await asyncio.to_thread(self._catalog.reload)
            failed=[e for e in self._catalog.errors if e.split(':')[0] in installed]
            ready=[m for m in installed if m in self._catalog.models]
            if failed and not ready:
                for name in installed: shutil.rmtree(model_dir/name,ignore_errors=True)
                await asyncio.to_thread(self._catalog.reload)
                return web.json_response({'error':'The model files are incomplete: '+failed[0].split(': ',1)[-1]},status=400)
            current=self._model_selection.state['model_id']
            if ready and (current is None or current not in self._catalog.models):
                self._model_selection.change({'model_id':ready[0]})
            await self._broadcast_to_ui({'type':'model_catalog',**self._catalog.public()})
            await self._broadcast_to_ui(self._model_selection.payload())
        logger.info('Imported Live2D model(s): %s',', '.join(ready))
        return web.json_response({'installed':ready,'models':[m.public() for m in self._catalog.models.values()],
                                  'selected':self._model_selection.state['model_id']})
