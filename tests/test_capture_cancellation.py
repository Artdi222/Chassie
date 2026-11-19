import asyncio
import threading
from types import SimpleNamespace

import pytest

from orchestrator import Orchestrator


async def wait_for_thread(event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(.002)


@pytest.mark.asyncio
@pytest.mark.parametrize('first_muted,last_muted', [(True, False), (False, True)])
async def test_cancel_joins_native_mic_change_before_latest_state_applies(first_muted, last_muted):
    app = object.__new__(Orchestrator)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    state = {'muted': not first_muted}
    def set_muted(value):
        calls.append(value)
        if len(calls) == 1:
            entered.set()
            release.wait(3)
        state['muted'] = value
        finished.set()
    app._stt = SimpleNamespace(set_muted=set_muted)
    app._mic_enabled = not first_muted
    app._capture_paused = False
    old = asyncio.create_task(app._sync_capture())
    newest = None
    try:
        await wait_for_thread(entered)
        old.cancel()
        app._mic_enabled = not last_muted
        newest = asyncio.create_task(app._sync_capture())
        await asyncio.sleep(.03)
        assert not newest.done(), 'Latest capture sync must wait for the canceled native worker'
        release.set()
        await asyncio.gather(old, return_exceptions=True)
        await asyncio.wait_for(newest, 2)
        assert old.cancelled()
        assert state['muted'] is last_muted
        assert calls == [first_muted, last_muted]
    finally:
        release.set()
        await asyncio.gather(old, *( [newest] if newest else []), return_exceptions=True)
        await wait_for_thread(finished)


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_release_mic_serialization_early():
    app = object.__new__(Orchestrator)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def set_muted(value):
        calls.append(value)
        if len(calls) == 1:
            entered.set(); release.wait(3)
    app._stt = SimpleNamespace(set_muted=set_muted)
    app._mic_enabled, app._capture_paused = True, True
    old = asyncio.create_task(app._sync_capture())
    newest = None
    try:
        await wait_for_thread(entered)
        old.cancel()
        await asyncio.sleep(0)
        old.cancel()
        app._capture_paused = False
        newest = asyncio.create_task(app._sync_capture())
        await asyncio.sleep(.03)
        assert calls == [True]
        release.set()
        await asyncio.gather(old, return_exceptions=True)
        await asyncio.wait_for(newest, 2)
        assert calls == [True, False]
    finally:
        release.set()
        await asyncio.gather(old, *( [newest] if newest else []), return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_during_first_playback_mute_waits_then_restores_capture(tmp_path):
    from unittest.mock import Mock, AsyncMock
    import numpy as np

    entered, release = threading.Event(), threading.Event()
    stt = Mock(epoch=0, muted=False, error=None, is_listening=Mock(return_value=False))
    def set_muted(value):
        if value:
            entered.set(); release.wait(3)
        stt.muted = value
    stt.set_muted.side_effect = set_muted
    hermes = Mock()
    async def stream(*args, **kwargs):
        yield '[happy] First sentence. '
    hermes.stream_message = stream
    async def synthesize(text):
        yield np.ones(480)
    player = Mock(cancel_utterance=Mock(), flush_effects=AsyncMock())
    app = Orchestrator({'audio': {'output_sample_rate': 24000},
                        'companion': {'memory_path': str(tmp_path / 'memory.sqlite')}},
                       components={'stt': stt, 'hermes': hermes,
                                   'tts': Mock(synthesize_stream=synthesize), 'player': player,
                                   'analyzer': Mock()})
    app._broadcast_to_ui = AsyncMock()
    app._turn_task = asyncio.create_task(app._run_turn({'text': 'test'}))
    turn = app._turn_task
    stop = None
    try:
        await wait_for_thread(entered)
        stop = asyncio.create_task(app.handle_control({'type': 'stop'}))
        await asyncio.sleep(.03)
        assert not stop.done()
        release.set()
        await asyncio.wait_for(stop, 2)
        assert turn.cancelled()
        assert app._mic_enabled and not app._capture_paused and not stt.muted
        player.begin_utterance.assert_not_called()
        hermes.complete_response.assert_not_called()
    finally:
        release.set()
        if not turn.done(): turn.cancel()
        await asyncio.gather(turn, *([stop] if stop else []), return_exceptions=True)
        app._memory.close()
