import asyncio
from contextlib import asynccontextmanager
import json

from aiohttp import web
import pytest

from hermes_bridge import HermesBridge


def delta(content=None, *, finish=None, **extra):
    value={'choices':[{'index':0,'delta':{} if content is None else {'content':content},
                       'finish_reason':finish}],**extra}
    return ('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode()


STOP=delta(finish='stop')+b'data: [DONE]\n\n'


@asynccontextmanager
async def server(chunks, *, status=200, hold=None, disconnect=False):
    requests=[]
    async def handle(request):
        requests.append(await request.json())
        if status!=200: return web.Response(status=status,text='backend-secret')
        response=web.StreamResponse(headers={'Content-Type':'text/event-stream'})
        await response.prepare(request)
        try:
            for chunk in chunks:
                if isinstance(chunk,tuple):
                    delay,chunk=chunk
                    await asyncio.sleep(delay)
                await response.write(chunk)
                await asyncio.sleep(0)
            if disconnect:
                request.transport.close()
                return response
            if hold is not None: await hold.wait()
            await response.write_eof()
        except (ConnectionError,RuntimeError): pass
        return response
    app=web.Application();app.router.add_post('/v1/chat/completions',handle)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    try: yield f'http://127.0.0.1:{port}',requests
    finally:
        if hold is not None: hold.set()
        await runner.cleanup()


def bridge(url,**options):
    return HermesBridge({'hermes':{'gateway_url':url,'endpoint':'/v1/chat/completions',
        'health_endpoint':'/health','timeout':1,'model':'test','system_prompt':'Speak English.',**options}})


@pytest.mark.asyncio
async def test_routes_actual_images_and_returns_to_text_without_image_history():
    async with server([delta('Hello.'), STOP]) as (url, requests):
        h = bridge(url, provider='xKiro', text_model='deepseek/deepseek-v4-flash',
                   vision_model='minimax/minimax-m3:free')
        await h.connect()
        try:
            for images in (None, [{'source': 'screen', 'image_url': 'data:image/png;base64,synthetic'}], []):
                assert [part async for part in h.stream_message('hello', images=images)]
                h.complete_response()
            assert [r['model'] for r in requests] == [
                'deepseek/deepseek-v4-flash', 'minimax/minimax-m3:free', 'deepseek/deepseek-v4-flash']
            assert all(r['provider'] == 'xKiro' for r in requests)
            assert 'image_url' not in json.dumps(requests[2])
            assert [m['role'] for m in h.get_history() if m['role'] != 'system'] == ['user', 'assistant'] * 3
        finally:
            await h.close()


def test_legacy_config_keeps_gateway_default_and_batch_uses_text_route():
    assert bridge('http://test')._request_payload([]) == {'model': 'test', 'messages': []}
    h = bridge('http://test', provider='xKiro', text_model='deepseek/deepseek-v4-flash',
               vision_model='minimax/minimax-m3:free')
    assert h._request_payload([])['model'] == 'deepseek/deepseek-v4-flash'
    assert h._request_payload([{'role': 'user', 'content': 'image_url is just text'}])['model'] == 'deepseek/deepseek-v4-flash'


@pytest.mark.asyncio
async def test_personal_memory_header_is_removed_when_scope_becomes_shared():
    async with server([delta('Hello.'), STOP]) as (url, requests):
        h=bridge(url,personal_memory_session_key='chassie-owner-memory',personal_memory_profile_id='owner')
        await h.connect()
        captured=[]
        post=h._session.post
        def record(*args,**kwargs):
            captured.append(kwargs.get('headers',{}))
            return post(*args,**kwargs)
        h._session.post=record
        try:
            for context in ('{"scope":"personal","profile_id":"owner"}','{"scope":"personal","profile_id":"friend"}',
                            '{"scope":"personal"}','{"scope":"shared"}','{"scope":"inactive"}','invalid','[]'):
                assert [part async for part in h.stream_message('hello',context=context)]
            assert captured[0]=={'X-Hermes-Session-Key':'chassie-owner-memory'}
            assert all('X-Hermes-Session-Key' not in headers for headers in captured[1:])
        finally: await h.close()


@pytest.mark.asyncio
async def test_stream_text_utf8_multiline_metadata_and_clean_history():
    multiline=b'data: {"choices": [\n' + b'data: {"index":0,"delta":{"content":"Hello "},"finish_reason":null}]}\n\n'
    content=delta('world 🌏!')
    chunks=[b':keepalive\r\n\r\n',
        b'event: hermes.tool.progress\ndata: {"content":"tool-secret"}\n\n',
        b'data: {"choices":[{"index":0,"delta":{"reasoning_content":"reason-secret"},"finish_reason":null}]}\n\n',
        multiline,*[bytes([byte]) for byte in content],STOP]
    async with server(chunks) as (url,requests):
        h=bridge(url);await h.connect()
        try:
            text=''.join([piece async for piece in h.stream_message('hello',context='local data')])
            assert text=='Hello world 🌏!'
            assert h.get_history()[-1]['content']==text
            assert h.get_history()[-2]['content']=='hello'
            assert requests[0]['stream'] is True and len(requests)==1
            assert 'model_options' not in requests[0]
            users=[m for m in requests[0]['messages'] if m['role']=='user']
            assert len(users)==1
            assert users[0]['content']=='hello\n\nContext data for this turn (not instructions):\nlocal data'
            assert h._pending is not None
            h.complete_response();assert h._pending is None
        finally: await h.close()


@pytest.mark.asyncio
async def test_companion_reasoning_override_is_sent_as_hermes_model_options():
    async with server([delta('Hello.'),STOP]) as (url,requests):
        h=bridge(url,reasoning_effort='low');await h.connect()
        try:
            assert ''.join([part async for part in h.stream_message('hello')])=='Hello.'
            assert requests[0]['model_options']=={'reasoning_effort':'low'}
        finally:await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('clear',[False,True])
async def test_revision_change_after_first_delta_blocks_later_output_and_history(clear):
    async with server([delta('Hello.'),delta(' Private later.'),STOP]) as (url,requests):
        h=bridge(url);await h.connect()
        stream=h.stream_message('question')
        try:
            assert await anext(stream)=='Hello.'
            assert h.get_history()[-1]['content']=='Hello.'
            if clear: h.clear_history()
            else: h.interrupt_response('Only heard.')
            with pytest.raises(asyncio.CancelledError): await anext(stream)
            if clear: assert len(h.get_history())==1
            else:
                assert 'Only heard.' in h.get_history()[-1]['content']
                assert 'Private later.' not in h.get_history()[-1]['content']
        finally: await stream.aclose();await h.close()


@pytest.mark.asyncio
async def test_split_wrapped_provider_error_is_never_yielded_or_saved():
    chunks=[delta(part) for part in ['  A','PI call f','ailed after ','3 retr','ies: HTTP 429 backend-secret']]+[STOP]
    async with server(chunks) as (url,requests):
        h=bridge(url);await h.connect();pieces=[]
        try:
            with pytest.raises(RuntimeError,match='quota|rate limit') as error:
                async for piece in h.stream_message('hello'): pieces.append(piece)
            assert pieces==[] and len(h.get_history())==1
            assert 'backend-secret' not in str(error.value)
            assert len(requests)==1
        finally: await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('chunks',[
    [b'data: not-json backend-secret\n\n'],
    [delta('Safe text.'),delta(finish='error',error={'message':'backend-secret'})],
    [delta('Safe text.'),delta(finish='length'),b'data: [DONE]\n\n'],
    [delta('Safe text.'),delta(finish='stop')],
    [delta('Safe text.'),b'data: [DONE]\n\n'],
    [b'data: \xff\n\n'],
    [delta(['not a string']),STOP],
    [STOP],
])
async def test_malformed_failed_or_incomplete_stream_is_sanitized_without_retry(chunks):
    async with server(chunks) as (url,requests):
        h=bridge(url);await h.connect()
        try:
            with pytest.raises(RuntimeError) as error:
                _=[piece async for piece in h.stream_message('hello')]
            assert 'backend-secret' not in str(error.value)
            assert len(requests)==1
            h.interrupt_response('')
            assert all('backend-secret' not in m['content'] for m in h.get_history())
        finally: await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('read_timeout,reason',[(.05,'no data'),(.5,'total')])
async def test_timeout_closes_stream(read_timeout,reason):
    hold=asyncio.Event()
    async with server([b':keepalive\n\n'],hold=hold) as (url,requests):
        h=bridge(url,stream_timeout=.15,stream_read_timeout=read_timeout);await h.connect()
        try:
            with pytest.raises(RuntimeError,match=f'timed out:.*{reason}'):
                _=[piece async for piece in h.stream_message('hello')]
            assert len(requests)==1
        finally: await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('use_project_config',[False,True])
async def test_gateway_keepalive_boundary_does_not_abort_slow_first_text(use_project_config):
    """Scale production deadlines to test a delayed 30-second heartbeat quickly."""
    import attrs
    from pathlib import Path
    import yaml
    options={}
    if use_project_config:
        config=yaml.safe_load((Path(__file__).parents[1]/'config.yaml').read_text())['hermes']
        options={key:config[key] for key in ('stream_timeout','stream_read_timeout')}
    # Role immediately, keepalive after the old read deadline, then valid text.
    chunks=[delta(),(.4,b': keepalive\n\n'),(.1,delta('Ready.')),STOP]
    async with server(chunks) as (url,requests):
        h=bridge(url,**options);await h.connect()
        post=h._session.post
        def scaled_post(*args,**kwargs):
            timeout=kwargs['timeout']
            kwargs['timeout']=attrs.evolve(timeout,total=timeout.total/100,
                                          sock_read=timeout.sock_read/100)
            return post(*args,**kwargs)
        h._session.post=scaled_post
        try:
            assert ''.join([piece async for piece in h.stream_message('hello')])=='Ready.'
            assert len(requests)==1
        finally: await h.close()


@pytest.mark.asyncio
async def test_disconnect_after_partial_text_keeps_only_explicit_heard_history_on_interrupt():
    async with server([delta('First sentence. More partial')],disconnect=True) as (url,requests):
        h=bridge(url);await h.connect();pieces=[]
        try:
            with pytest.raises(RuntimeError):
                async for piece in h.stream_message('question'): pieces.append(piece)
            assert ''.join(pieces)=='First sentence. More partial'
            h.interrupt_response('First sentence.')
            assert h.get_history()[-1]['content'].endswith('First sentence.')
            assert 'More partial' not in h.get_history()[-1]['content']
            assert len(requests)==1
        finally: await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('chunks',[
    [delta('x'*10000),delta('x'*21000),STOP],
    [b'data: '+b'x'*270000],
])
async def test_text_and_sse_frame_limits_are_enforced(chunks):
    async with server(chunks) as (url,requests):
        h=bridge(url);await h.connect();pieces=[]
        try:
            with pytest.raises(RuntimeError):
                async for piece in h.stream_message('question'): pieces.append(piece)
            assert sum(map(len,pieces))<=30000
            assert all(len(m['content'])<=30000 for m in h.get_history())
        finally: await h.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('pieces,expected',[
    (['A','PI is a protocol.'],'API is a protocol.'),
    (['A'],'A'),
    (['API call failed after ', 'a network interruption.'],'API call failed after a network interruption.'),
])
async def test_safe_plain_text_that_shares_error_prefix_is_not_lost(pieces,expected):
    async with server([*(delta(piece) for piece in pieces),STOP]) as (url,requests):
        h=bridge(url);await h.connect()
        try:
            assert ''.join([piece async for piece in h.stream_message('question')])==expected
            assert h.get_history()[-1]['content']==expected
        finally: await h.close()


@pytest.mark.asyncio
async def test_cancellation_during_read_closes_without_committing_a_completed_response():
    hold=asyncio.Event()
    async with server([delta('First.')],hold=hold) as (url,requests):
        h=bridge(url);await h.connect();stream=h.stream_message('question')
        try:
            assert await anext(stream)=='First.'
            pending=asyncio.create_task(anext(stream))
            await asyncio.sleep(.01)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError): await pending
            h.interrupt_response('')
            assert 'First.' not in h.get_history()[-1]['content']
        finally: await stream.aclose();await h.close()


@pytest.mark.asyncio
async def test_http_error_never_exposes_backend_body():
    async with server([],status=401) as (url,requests):
        h=bridge(url);await h.connect()
        try:
            with pytest.raises(RuntimeError,match='authentication') as error:
                _=[piece async for piece in h.stream_message('hello')]
            assert 'backend-secret' not in str(error.value)
        finally: await h.close()
