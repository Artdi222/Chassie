import asyncio
import base64
import json
from unittest.mock import Mock

import numpy as np
import pytest
from aiohttp import web

from companion.memory import MemoryStore
from face_identity import FaceIdentity, face_command, match_template
from visual_context import VisualContext, encode_frame, capture_screen
from hermes_bridge import HermesBridge
from test_hermes_tts import CONFIG
from test_orchestrator import app, playback_fixture


def embedding(index=0):
    values = [0.0] * 128
    values[index] = 1.0
    return values


def test_templates_require_consent_persist_and_cascade_with_profile(tmp_path):
    path = tmp_path / 'memory.sqlite'
    with MemoryStore(path) as store:
        profile = store.create_profile('Owner', consent=True)
        with pytest.raises(ValueError, match='consent'):
            store.save_face(profile.id, embedding(), consent=False)
        for invalid in ([1.0], [float('nan')] * 128, [0.0] * 128):
            with pytest.raises(ValueError):
                store.save_face(profile.id, invalid, consent=True)
        store.save_face(profile.id, embedding(), consent=True)
    with MemoryStore(path) as store:
        assert store.list_faces()[0]['name'] == 'Owner'
        assert match_template(embedding(), store.list_faces())['profile_id'] == profile.id
        assert match_template(embedding(1), store.list_faces()) is None
        store.delete_profile(profile.id)
        assert store.list_faces() == []


def test_ambiguous_and_invalid_face_matches_are_unknown():
    templates = [{'profile_id': str(i), 'name': str(i), 'embedding': embedding()} for i in range(2)]
    assert match_template(embedding(), templates) is None
    assert match_template([float('nan')] * 128, templates) is None


def test_only_explicit_whole_message_face_commands_enroll():
    assert face_command('ingat wajahku sebagai Artdi') == ('remember', 'Artdi')
    assert face_command('remember my face as Artdi.') == ('remember', 'Artdi')
    assert face_command('lupakan wajah Artdi') == ('forget', 'Artdi')
    assert face_command('what does "remember my face as Artdi" mean?') is None
    assert face_command('my name is Artdi') is None


def test_capture_expiration_failure_and_stop_clear_snapshots(tmp_path):
    now = [10.0]
    with MemoryStore(tmp_path / 'memory.sqlite') as memory:
        vision = VisualContext({'vision': {'camera_enabled': True, 'screen_enabled': True}}, memory, clock=lambda: now[0])
        vision._record('camera', 'data:image/jpeg;base64,test', 10)
        vision._record('screen', 'data:image/jpeg;base64,test', 10, 'A GUI window')
        vision._candidate = (embedding(), 10)
        assert len(vision.snapshot()) == 2
        assert vision.enrollment() == embedding()
        now[0] = 16
        assert vision.snapshot() == []
        with pytest.raises(ValueError, match='not saved'):
            vision.enrollment()
        vision._record('screen', 'test', 16)
        vision._fail('screen', 'No permission')
        assert vision.snapshot() == []
        assert vision.status()['screen']['error'] == 'No permission'
        vision.stop()
        vision._record('screen', 'late result', 16)
        assert vision.snapshot() == []


def test_forgetting_immediately_invalidates_old_recognition(tmp_path):
    with MemoryStore(tmp_path / 'memory.sqlite') as memory:
        profile = memory.create_profile('Owner', consent=True)
        memory.save_face(profile.id, embedding(), consent=True)
        vision = VisualContext({}, memory, clock=lambda: 10)
        vision._record('camera', 'test', 10)
        vision._identity = {'matches': [match_template(embedding(), memory.list_faces())], 'face_count': 1, 'ready': True, 'error': None}
        vision._identity_revision = memory.revision
        assert vision.status()['identity']['matches']
        memory.delete_face(profile.id)
        assert vision.status()['identity']['matches'] == []


def test_camera_encoding_is_bounded_jpeg_and_native_recognizer_handles_no_face():
    import cv2
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    data = encode_frame(frame, 320)
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(data.split(',')[1]), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (240, 320, 3)
    from face_identity import MODEL_DIR, DETECTOR, RECOGNIZER
    if all((MODEL_DIR / name).exists() for name in (DETECTOR, RECOGNIZER)):
        assert FaceIdentity().observe(frame, []) == ([], None)


def test_missing_identity_weights_preserve_presence_detection(tmp_path):
    from types import SimpleNamespace
    detector = FaceIdentity(tmp_path)
    assert not detector.ready
    detector.close()
    detector.fallback = Mock(detect=Mock(return_value=SimpleNamespace(face_landmarks=[[], []])))
    matches, candidate = detector.observe(np.zeros((480, 640, 3), dtype=np.uint8), [])
    assert matches == [None, None] and candidate is None


def test_model_cache_is_relative_to_project_not_launch_directory(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    with MemoryStore(tmp_path / 'memory.sqlite') as memory:
        vision = VisualContext({'vision': {'model_dir': '.chassie/vision-models'}}, memory)
        assert vision.model_dir == Path(__file__).resolve().parents[1] / '.chassie/vision-models'


def test_recognition_failure_keeps_camera_frame_and_releases_device(tmp_path, monkeypatch):
    with MemoryStore(tmp_path / 'memory.sqlite') as memory:
        vision = VisualContext({}, memory, clock=lambda: 10)
        cap = Mock(); cap.isOpened.return_value = True
        reads = []
        def read():
            if reads:
                vision._stop.set()
            reads.append(True)
            return True, np.zeros((480, 640, 3), dtype=np.uint8)
        cap.read.side_effect = read
        recognizer = Mock(ready=True, error=None)
        recognizer.observe.side_effect = RuntimeError('Synthetic inference failure')
        monkeypatch.setattr('visual_context.FaceIdentity', lambda _: recognizer)
        monkeypatch.setattr('cv2.VideoCapture', lambda _: cap)
        vision._camera_loop()
        assert vision.snapshot()[0]['source'] == 'camera'
        assert vision.status()['identity']['presence_ready'] is False
        cap.release.assert_called_once()
        recognizer.close.assert_called_once()


def test_wayland_captures_visible_gui_on_active_monitor(monkeypatch):
    import cv2
    calls = []
    _, png = cv2.imencode('.png', np.zeros((120, 160, 3), dtype=np.uint8))
    def run(command, **kwargs):
        calls.append(command)
        if command[-1] == 'activewindow':
            return json.dumps({'class': 'editor', 'title': 'Work', 'monitor': 2}).encode()
        if command[-1] == 'monitors':
            return json.dumps([{'id': 2, 'name': 'DP-1'}]).encode()
        return png.tobytes()
    monkeypatch.setenv('WAYLAND_DISPLAY', 'test')
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE', 'test')
    monkeypatch.setattr('visual_context.shutil.which', lambda _: '/usr/bin/test')
    monkeypatch.setattr('visual_context.subprocess.check_output', run)
    image, title = capture_screen()
    assert calls[-1] == ['grim', '-o', 'DP-1', '-t', 'png', '-']
    assert title == 'editor — Work'
    assert image.startswith('data:image/jpeg;base64,')


@pytest.mark.asyncio
async def test_visual_snapshots_reach_real_sse_contract_but_not_history():
    image = {'source': 'screen', 'title': 'Synthetic GUI', 'image_url': encode_frame(np.zeros((50, 50, 3), dtype=np.uint8))}
    seen = []
    async def endpoint(request):
        seen.append(await request.json())
        response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
        await response.prepare(request)
        await response.write(b'data: {"choices":[{"delta":{"content":"[neutral] A black image."},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        return response
    server = web.Application(); server.router.add_post('/v1/chat/completions', endpoint)
    runner = web.AppRunner(server); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    config = {**CONFIG, 'hermes': {**CONFIG['hermes'], 'gateway_url': f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'}}
    bridge = HermesBridge(config); await bridge.connect()
    try:
        assert [delta async for delta in bridge.stream_message('What is visible?', images=[image])]
        content = seen[0]['messages'][-1]['content']
        assert content[-1] == {'type': 'image_url', 'image_url': {'url': image['image_url']}}
        assert bridge.get_history()[-2] == {'role': 'user', 'content': 'What is visible?'}
        assert 'base64' not in json.dumps(bridge._messages)
    finally:
        await bridge.close(); await runner.cleanup()


@pytest.mark.asyncio
async def test_voice_turn_uses_snapshots_when_requested_and_releases_them(app):
    playback = playback_fixture(app); playback.first_release.set()
    frames = [{'source': 'camera', 'image_url': 'synthetic'}]
    status={'camera': {'available': True}, 'identity': {'face_count': 1}}
    app._vision = Mock(request_context=Mock(return_value=(frames,status)), status=Mock(return_value=status))
    async def stream(text, **kwargs):
        assert kwargs['images'] == frames
        yield '[happy] Hello.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'Can you see me?', 'source': 'voice'})
    assert app._spoken.strip() == 'Hello.'
    assert app._turn_images == []


def test_face_enrollment_does_not_unlock_personal_memories_and_forget_works(app):
    app._vision = Mock(enrollment=Mock(return_value=embedding()))
    assert 'remembered locally' in app._apply_face_command('remember', 'Owner')
    assert app._memory.list_faces()[0]['name'] == 'Owner'
    assert app._session_context.owner_profile_id is None
    assert 'deleted locally' in app._apply_face_command('forget', 'Owner')
    assert app._memory.list_faces() == []
    assert len(app._memory.list_profiles()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('identity', [
    {'face_count': 2, 'presence_ready': True},
    {'face_count': 0, 'presence_ready': False},
])
async def test_presence_gates_private_context_before_background_monitor(app, identity):
    playback = playback_fixture(app); playback.first_release.set()
    profile = app._memory.create_profile('Owner', consent=True)
    app._session_context.set_owner(profile.id)
    app._memory.add_memory(profile.id, 'private preference', source='test', consent=True)
    status = {'camera': {'enabled': True, 'available': True}, 'identity': identity}
    app._vision = Mock(request_context=Mock(return_value=([], status)), status=Mock(return_value=status))
    async def stream(text, **kwargs):
        assert 'private preference' not in kwargs['context']
        assert json.loads(kwargs['context'])['scope'] == 'shared'
        app._hermes.clear_history.assert_called_once()
        yield '[neutral] Hello everyone.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'Hello', 'source': 'text'})
    assert app._spoken.strip() == 'Hello everyone.'


@pytest.mark.asyncio
async def test_forget_drops_cached_match_in_the_same_model_request(app):
    playback = playback_fixture(app); playback.first_release.set()
    profile = app._memory.create_profile('Owner', consent=True)
    app._memory.save_face(profile.id, embedding(), consent=True)
    status = {'camera': {'enabled': True, 'available': True},
              'identity': {'face_count': 1, 'presence_ready': True, 'matches': [{'name': 'Owner'}]}}
    app._vision = Mock(request_context=Mock(return_value=([], status)), status=Mock(return_value=status))
    async def stream(text, **kwargs):
        context = json.loads(kwargs['context'])
        assert 'vision' not in context
        assert 'images' not in kwargs
        assert app._memory.list_faces() == []
        yield '[neutral] Your face template was deleted.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'forget the face of Owner', 'source': 'text'})
    assert app._spoken.strip() == 'Your face template was deleted.'


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['text', 'voice'])
async def test_visual_request_selects_source_and_never_carries_into_next_turn(app, source):
    playback = playback_fixture(app); playback.first_release.set()
    frames = [{'source': name, 'image_url': 'synthetic-' + name, 'title': name}
              for name in ('camera', 'screen')]
    status = {'camera': {'available': True}, 'screen': {'available': True},
              'identity': {'face_count': 1, 'matches': [{'name': 'Private face hint'}]}}
    app._vision = Mock(request_context=Mock(return_value=(frames, status)), status=Mock(return_value=status))
    seen = []
    async def stream(text, **kwargs):
        seen.append(kwargs)
        yield '[neutral] Hello.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'Tolong lihat layar aku', 'source': source})
    assert seen[0]['images'] == [frames[1]]
    context = json.loads(seen[0]['context'])
    assert 'screen' in context['vision']
    assert 'camera' not in context['vision'] and 'identity' not in context['vision']
    await app._run_turn({'text': 'Terima kasih', 'source': source})
    assert 'images' not in seen[1] and 'vision' not in json.loads(seen[1]['context'])
    app._vision.request_context.assert_called_once()


@pytest.mark.asyncio
async def test_requested_unavailable_source_does_not_substitute_other_images(app):
    playback = playback_fixture(app); playback.first_release.set()
    status = {'camera': {'available': True}, 'screen': {'available': False, 'enabled': False}}
    app._vision = Mock(request_context=Mock(return_value=(
        [{'source': 'camera', 'image_url': 'synthetic'}], status)), status=Mock(return_value=status))
    async def stream(text, **kwargs):
        assert 'images' not in kwargs
        assert json.loads(kwargs['context'])['vision']['screen']['available'] is False
        yield '[neutral] Screen is unavailable.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'Check my screen', 'source': 'text'})
    assert app._spoken.strip() == 'Screen is unavailable.'
