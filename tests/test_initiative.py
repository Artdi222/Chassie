import asyncio
import datetime
import json
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from ambient import ChangeWatcher, SceneWatcher
from bilingual import BilingualChunker
from chassie_core.initiative import InitiativeState, MODES, PREFIX, decide, initiative_text
from desktop.motion import HeadMotion
from test_orchestrator import app, playback_fixture  # noqa: F401  (fixture)

DAY = datetime.datetime(2026, 11, 18, 15, 0)
PAIR = {'emotion': 'happy', 'ja': 'こんにちは。', 'en': 'Hello.'}


def observe(state, now, **kw):
    args = dict(owner_alone=True, face_visible=True, camera_on=True, mic_on=True, clock_time=DAY)
    args.update(kw)
    return decide(state, now, **args)


def test_skip_line_is_a_valid_silent_reply():
    chunker = BilingualChunker('en')
    assert chunker.feed('{"skip":true}\n') == [('skip',)]
    assert chunker.finish() == []
    chunker = BilingualChunker('en')
    chunker.feed(json.dumps(PAIR, ensure_ascii=False) + '\n')
    with pytest.raises(ValueError):
        chunker.feed('{"skip":true}\n')


def test_look_action_is_allowed_after_speech_and_validated():
    chunker = BilingualChunker('en')
    chunker.feed(json.dumps(PAIR, ensure_ascii=False) + '\n')
    assert chunker.feed('{"action":"look","source":"camera"}\n') == [('action', 'look', 'camera')]
    for bad in ('{"action":"look","source":"files"}\n', '{"action":"look","name":"x"}\n'):
        with pytest.raises(ValueError):
            BilingualChunker('en').feed(bad)


def test_quiet_check_in_waits_for_silence_and_respects_privacy_and_presence():
    quiet = MODES['normal']['quiet']
    state = InitiativeState(last_activity=0)
    assert observe(state, quiet - 1) is None
    assert observe(state, quiet)[0] == 'quiet'
    assert observe(state, quiet, owner_alone=False) is None
    assert observe(state, quiet, face_visible=False) is None
    assert observe(state, quiet, mic_on=False)[0] == 'quiet'  # Typing with the mic off still gets check-ins.
    assert observe(state, quiet, camera_on=False, face_visible=False)[0] == 'quiet'
    assert observe(InitiativeState(mode='off', last_activity=0), 10_000) is None


def test_unanswered_check_ins_back_off_and_cooldown_applies():
    quiet = MODES['normal']['quiet']
    state = InitiativeState(last_activity=0, unanswered=2)
    assert observe(state, quiet * 2) is None
    assert observe(state, quiet * 4)[0] == 'quiet'
    state = InitiativeState(last_activity=0, last_initiative=quiet * 4 - 10)
    assert observe(state, quiet * 4) is None


def test_look_again_bypasses_quiet_rules_but_not_owner_scope():
    state = InitiativeState(mode='off', last_activity=100, look={'source': 'camera', 'due': 104})
    assert observe(state, 103) is None
    assert observe(state, 104) == ('look', 'camera', {'camera'})
    assert observe(state, 104, owner_alone=False) is None
    state.look = {'source': 'camera', 'due': None}  # Still speaking: not due yet.
    assert observe(state, 10_000) is None


def test_event_priorities():
    state = InitiativeState(last_activity=0, events=[(5, 'vase')], pending_return=True)
    assert observe(state, 30)[0] == 'returned'
    state.pending_return = False
    assert observe(state, 30)[:2] == ('noticed', 'vase')
    assert observe(state, 10) is None  # Too soon after the user spoke.
    late = datetime.datetime(2026, 11, 18, 1, 30)
    assert observe(InitiativeState(last_activity=0), 61, clock_time=late)[0] == 'late_night'
    state = InitiativeState(last_activity=0, app='Krita', app_since=0)
    assert observe(state, 95)[:2] == ('app', 'Krita')
    state.app_mentioned = 'Krita'
    assert observe(state, 95)[0] == 'quiet'  # Already mentioned: falls through to a check-in.
    assert initiative_text('quiet', 3, DAY).startswith(PREFIX)


def test_scene_watcher_ignores_baseline_and_flicker():
    watcher = SceneWatcher(warmup=5, forget=60, confirm=2)
    assert watcher.feed({'cup', 'person'}, 0) == []
    assert watcher.feed({'vase'}, 10) == []
    assert watcher.feed({'vase', 'cup'}, 12) == ['vase']  # cup was baseline
    assert watcher.feed({'vase'}, 14) == []  # reported once
    assert watcher.feed({'tv', 'person'}, 16) == []  # ignored labels


def test_change_watcher_needs_a_persistent_change():
    watcher = ChangeWatcher(threshold=20, confirm=2, cooldown=60)
    dark, bright = np.zeros((24, 32)), np.full((24, 32), 200.0)
    assert not watcher.feed(dark, 0)
    assert not watcher.feed(bright, 2)
    assert not watcher.feed(dark, 4)  # brief motion
    assert not watcher.feed(bright, 6)
    assert watcher.feed(bright, 8)
    assert not watcher.feed(dark, 10) and not watcher.feed(dark, 12)  # cooldown


def test_head_motion_eases_toward_status_pose():
    motion = HeadMotion(['ParamAngleZ', 'ParamAngleY', 'ParamMouthOpenY'])
    assert set(motion.step('thinking', 0.0)) == {'ParamAngleY', 'ParamAngleZ'}
    for i in range(1, 60):
        pose = motion.step('thinking', i / 30)
    assert pose['ParamAngleZ'] < -4 and pose['ParamAngleY'] > 3


def silent_tts(app, spoken):
    async def synthesize(text, *, emotion):
        spoken.append(text)
        yield np.ones(480)
    app._tts.synthesize_stream = synthesize
    app._bilingual = True


@pytest.mark.asyncio
async def test_skipped_initiative_says_nothing_and_leaves_no_history(app):
    playback = playback_fixture(app)
    playback.first_release.set()
    spoken = []
    silent_tts(app, spoken)

    async def stream(*a, **kw):
        yield '{"skip":true}\n'
    app._hermes.stream_message = stream
    app._hermes.discard_response = Mock()
    app._hermes.complete_response = Mock()
    await app._run_turn({'text': PREFIX + 'quiet', 'source': 'initiative', 'visual': []})
    assert spoken == []
    app._hermes.discard_response.assert_called_once()
    app._hermes.complete_response.assert_not_called()
    sent = [call.args[0] for call in app._broadcast_to_ui.call_args_list]
    assert not any(m.get('type') == 'chat' and m.get('role') == 'user' for m in sent)


@pytest.mark.asyncio
async def test_look_action_schedules_a_fresh_snapshot(app):
    playback = playback_fixture(app)
    playback.first_release.set()
    silent_tts(app, [])
    app._vision = Mock(camera_enabled=True)
    app._vision.status.return_value = {'camera': {'available': True}, 'identity': {'face_count': 1}}
    app._visual_guest_reason = Mock(return_value=None)

    async def stream(*a, **kw):
        yield json.dumps({'emotion': 'curious', 'ja': 'もっと近くで見せて。', 'en': 'Bring it closer.'},
                         ensure_ascii=False) + '\n'
        yield '{"action":"look","source":"camera"}\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'look at these flowers', 'source': 'text'})
    look = app._initiative.look
    assert look['source'] == 'camera' and look['due'] >= app._initiative.last_activity + 3.9
    app._note_activity(user=True)  # The user talking again cancels the pending look.
    assert app._initiative.look is None


@pytest.mark.asyncio
async def test_slow_first_sentence_gets_a_thinking_filler(app):
    playback = playback_fixture(app)
    playback.first_release.set()
    spoken = []
    silent_tts(app, spoken)
    app._thinking_filler = .05

    async def stream(*a, **kw):
        await asyncio.sleep(.2)
        yield json.dumps(PAIR, ensure_ascii=False) + '\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'hi', 'source': 'text'})
    assert spoken == ['えっとね…', 'こんにちは。']


def test_discard_response_removes_the_silent_exchange():
    from hermes_bridge import HermesBridge
    from test_hermes_tts import CONFIG
    bridge = HermesBridge(CONFIG)
    base = len(bridge._messages)
    bridge._messages += [{'role': 'user', 'content': PREFIX + 'x'}, {'role': 'assistant', 'content': '{"skip":true}'}]
    bridge._pending = (bridge._revision, len(bridge._messages) - 1)
    bridge.discard_response()
    assert len(bridge._messages) == base and bridge._pending is None


def test_recall_always_includes_profile_and_recent_facts_and_dedupes_notes(app):
    profile = app._memory.create_profile('Artdi', consent=True)
    app._session_context.set_owner(profile.id)
    app._automatic_memory = True
    rows = [{'path': 'People/Artdi.md', 'content': 'Artdi profile', 'kind': 'vault_note', 'updated': '1'},
            *({'path': f'_generated/chassie/{i}.md', 'content': f'fact {i}', 'kind': 'user_statement',
               'updated': str(i)} for i in range(9))]
    hits = [{'path': 'Events/Long.md', 'content': f'chunk {i}'} for i in range(3)] + \
           [{'path': 'Events/Other.md', 'content': 'other'}, {'path': 'People/Artdi.md', 'content': 'dup'}]
    app._vault = Mock()
    app._vault.call.side_effect = lambda method, *a, **k: rows if method == 'list' else hits
    sources = [m['source'] for m in app._vault_recall('capek banget')]
    assert sources[0] == 'obsidian:People/Artdi.md'
    assert sources[1:7] == [f'obsidian:_generated/chassie/{i}.md' for i in (8, 7, 6, 5, 4, 3)]
    assert sources[7:] == ['obsidian:Events/Long.md', 'obsidian:Events/Other.md']
    assert [m['source'] for m in app._vault_recall('')] == sources[:7]  # Initiative: no search.
    app._vault.call.side_effect = ValueError('Vault unavailable')
    assert app._vault_recall('x') == []


def test_web_head_motion_matches_desktop_pose():
    import shutil
    import subprocess
    from pathlib import Path
    from desktop.motion import target_pose
    if not shutil.which('node') or subprocess.run(['node', '--version'], capture_output=True).returncode:
        pytest.skip('node unavailable or broken')
    script = Path(__file__).parents[1] / 'ui/pointer.js'
    js = ("globalThis.window={};globalThis.matchMedia=()=>({matches:false});"
          f"require({json.dumps(str(script))});"
          "console.log(JSON.stringify(['listening','thinking','speaking','idle'].map(s=>window.chassieHeadTarget(s,1.3))))")
    web = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True).stdout)
    for status, pose in zip(('listening', 'thinking', 'speaking', 'idle'), web):
        assert pose == pytest.approx(target_pose(status, 1.3))


def test_screen_change_and_screen_snapshots_in_initiatives():
    state = InitiativeState(last_activity=0, events=[(5, 'screen_changed'), (6, 'vase')])
    assert observe(state, 30, screen_on=True) == ('screen', None, {'screen'})
    assert observe(state, 30)[:2] == ('noticed', 'vase')  # Screen off: camera events only.
    quiet = MODES['normal']['quiet']
    assert observe(InitiativeState(last_activity=0), quiet, screen_on=True) == ('quiet', quiet // 60, {'screen'})
    state = InitiativeState(last_activity=0, app='Krita', app_since=0)
    assert observe(state, 95, screen_on=True)[2] == {'screen'}


def test_missed_face_frames_do_not_count_as_away(app):
    from types import SimpleNamespace
    status = {'camera': {'available': True}, 'identity': {'face_count': 0}}
    app._vision = SimpleNamespace(camera_enabled=True, status=lambda: status, pop_events=lambda: [])
    assert app._track_presence(100) is True  # Never seen yet: detection may simply be failing.
    status['identity']['face_count'] = 1
    assert app._track_presence(110) is True
    status['identity']['face_count'] = 0
    assert app._track_presence(200) is True  # 90 s of missed frames: still around.
    assert app._track_presence(300) is False  # Gone for longer than AWAY_SECONDS.


def test_screen_is_sent_only_when_it_changed(tmp_path):
    import cv2
    from visual_context import VisualContext
    from companion import MemoryStore
    vision = VisualContext({'vision': {'screen_enabled': True, 'screen_always': True}}, MemoryStore(str(tmp_path / 'm.sqlite')))
    assert not vision.screen_changed()  # Nothing captured yet.
    page = np.full((36, 64), 40, np.float32)
    vision._screen_thumb = page.copy()
    assert vision.screen_changed()  # Never sent before.
    vision.mark_screen_sent()
    typed = page.copy(); typed[10, 5:15] = 200  # A typed word.
    vision._screen_thumb = typed
    assert not vision.screen_changed()
    vision._screen_thumb = np.full((36, 64), 180, np.float32)  # A new page or app.
    assert vision.screen_changed()


@pytest.mark.asyncio
async def test_turn_attaches_screen_only_when_changed(app):
    from types import SimpleNamespace
    playback = playback_fixture(app); playback.first_release.set()
    silent_tts(app, [])
    changed = {'value': True}; sent = []
    frame = {'source': 'screen', 'image_url': 'data:image/jpeg;base64,AA==', 'captured_at': 0, 'title': ''}
    status = {'camera': {'available': False}, 'screen': {'available': True}, 'identity': {}}
    app._vision = SimpleNamespace(camera_enabled=False, screen_enabled=True, screen_always=True,
                                  screen_changed=lambda: changed['value'], mark_screen_sent=lambda: sent.append(1),
                                  request_context=lambda: ([frame], status), status=lambda: status)
    app._visual_guest_reason = Mock(return_value=None)
    seen = []

    async def stream(text, context='', mode='focus', images=None):
        seen.append((images, json.loads(context)))
        yield json.dumps(PAIR, ensure_ascii=False) + '\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'halo', 'source': 'text'})
    changed['value'] = False
    await app._run_turn({'text': 'terus?', 'source': 'text'})
    assert seen[0][0] == [frame] and sent == [1]
    assert not seen[1][0] and 'screen_unchanged' in seen[1][1]



@pytest.mark.asyncio
async def test_camera_every_turn_and_no_screen_when_only_chassie_is_open(app):
    from types import SimpleNamespace
    playback = playback_fixture(app); playback.first_release.set()
    silent_tts(app, [])
    camera = {'source': 'camera', 'image_url': 'data:image/jpeg;base64,AA==', 'captured_at': 0, 'title': ''}
    screen = {'source': 'screen', 'image_url': 'data:image/jpeg;base64,AA==', 'captured_at': 0, 'title': ''}
    status = {'camera': {'available': True}, 'screen': {'available': True}, 'identity': {}}
    app._vision = SimpleNamespace(camera_enabled=True, screen_enabled=True, screen_always=True, camera_always=True,
                                  screen_changed=lambda: True, screen_has_content=lambda: False,
                                  mark_screen_sent=lambda: None,
                                  request_context=lambda: ([camera, screen], status), status=lambda: status)
    app._visual_guest_reason = Mock(return_value=None)
    seen = []

    async def stream(text, context='', mode='focus', images=None):
        seen.append((images, json.loads(context)))
        yield json.dumps(PAIR, ensure_ascii=False) + '\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'halo', 'source': 'text'})
    assert seen[0][0] == [camera] and 'screen_unchanged' not in seen[0][1]


@pytest.mark.asyncio
async def test_model_looks_before_answering_and_turn_retries_with_the_photo(app):
    from types import SimpleNamespace
    playback = playback_fixture(app); playback.first_release.set()
    spoken = []
    silent_tts(app, spoken)
    camera = {'source': 'camera', 'image_url': 'data:image/jpeg;base64,AA==', 'captured_at': 0, 'title': ''}
    status = {'camera': {'available': True}, 'screen': {'available': False}, 'identity': {}}
    app._vision = SimpleNamespace(camera_enabled=True, screen_enabled=False, screen_always=False,
                                  request_context=lambda: ([camera], status), status=lambda: status)
    app._visual_guest_reason = Mock(return_value=None)
    seen = []

    async def stream(text, context='', mode='focus', images=None):
        seen.append(images)
        if not images:
            yield '{"action":"look","source":"camera"}\n'
            yield json.dumps(PAIR, ensure_ascii=False) + '\n'  # Never spoken: the turn restarts.
        else:
            yield '{"action":"look","source":"camera"}\n'  # Already looked: becomes look-again.
            yield json.dumps(PAIR, ensure_ascii=False) + '\n'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'gimana penampilanku?', 'source': 'text'})
    assert seen == [None, [camera]] and spoken == ['こんにちは。']
    app._hermes.discard_response.assert_called_once()
    assert app._initiative.look['source'] == 'camera'


def test_look_only_reply_without_trailing_newline_is_valid():
    from bilingual import BilingualChunker
    chunker = BilingualChunker('en')
    assert chunker.feed('{"action":"look","source":"camera"}') == []
    assert chunker.finish() == [('action', 'look', 'camera')]



def test_opening_hello_once_after_the_owner_sits_down():
    state = InitiativeState(last_activity=0, greeted=False, opened_at=0)
    assert observe(state, 3) is None  # Avatar and voice are still starting.
    assert observe(state, 10, face_visible=False) is None  # Wait until they are in front of the camera.
    assert observe(state, 10, mic_on=False)[0] == 'opened'
    assert observe(state, 10, camera_on=False, face_visible=False)[0] == 'opened'
    assert observe(InitiativeState(mode='off', greeted=False), 10) is None


@pytest.mark.asyncio
async def test_opening_hello_is_queued_once_and_skipped_if_the_owner_speaks_first(app):
    app._broadcast_to_ui = AsyncMock()
    app._init_initiative()
    state = app._initiative
    await app._start_initiative('opened', None, set())
    item = app._ui_input_queue.get_nowait()
    assert item['reason'] == 'opened' and 'just opened' in item['text'] and state.greeted
    app._init_initiative()
    app._note_activity(user=True)
    assert app._initiative.greeted
