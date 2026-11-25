import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from desktop.motion import HeadMotion, nod_offset
from speech.stt_engine import SpeechEvent, SpeechSegmenter
from test_orchestrator import app

FRAME = b'\0' * 960  # 30 ms at 16 kHz.


def run(segmenter, pattern):
    """Feed (speech?, seconds) runs; return event kinds with their times."""
    events, now = [], 0.0
    for speech, seconds in pattern:
        for _ in range(round(seconds / .03)):
            now += .03
            events += [(kind, round(now, 2)) for kind, _ in segmenter.feed(FRAME, speech, now)]
    return events


def test_one_pause_event_per_gap_after_real_speech():
    kinds = [k for k, _ in run(SpeechSegmenter(), [(True, 1.2), (False, .5), (True, .6), (False, .4), (False, 1.0)])]
    # Two mid-utterance gaps each give one pause; the final long silence ends the utterance.
    assert kinds == ['speech_start', 'speech_pause', 'speech_pause', 'utterance']
    short = [k for k, _ in run(SpeechSegmenter(), [(True, .5), (False, .5), (False, 1.0)])]
    assert 'speech_pause' not in short  # Too little speech yet for a nod.


def test_nod_is_a_single_soft_dip():
    assert nod_offset(None) == 0 and nod_offset(0) == 0 and nod_offset(.6) == 0
    assert nod_offset(.275) == pytest.approx(-7)
    motion = HeadMotion(['ParamAngleX', 'ParamAngleY', 'ParamAngleZ'])
    plain = motion.step('listening', 10.0)['ParamAngleY']
    nodding = HeadMotion(['ParamAngleX', 'ParamAngleY', 'ParamAngleZ']).step('listening', 10.0, nod_at=9.725)['ParamAngleY']
    assert nodding == pytest.approx(plain - 7)


@pytest.mark.asyncio
async def test_pause_while_listening_sends_a_rate_limited_backchannel(app):
    app._broadcast_to_ui = AsyncMock()
    app._mic_enabled = True
    app._current_status = 'listening'
    pause = SpeechEvent('speech_pause', app._stt.epoch, 0, 0)
    await app._handle_speech_event(pause)
    await app._handle_speech_event(pause)  # Within 1.6 s: no second nod.
    nods = [c for c in app._broadcast_to_ui.call_args_list if c.args[0] == {'type': 'backchannel'}]
    assert len(nods) == 1
    app._last_backchannel = 0.0
    app._current_status = 'speaking'
    await app._handle_speech_event(pause)
    assert len([c for c in app._broadcast_to_ui.call_args_list if c.args[0] == {'type': 'backchannel'}]) == 1


def test_web_nod_matches_desktop():
    if not shutil.which('node') or subprocess.run(['node', '--version'], capture_output=True).returncode:
        pytest.skip('node unavailable or broken')
    script = Path(__file__).parents[1] / 'ui/pointer.js'
    js = ("globalThis.window={};globalThis.matchMedia=()=>({matches:false});"
          f"require({json.dumps(str(script))});"
          "console.log(JSON.stringify([0,.1,.275,.5,.6].map(t=>window.chassieNodOffset(t))))")
    web = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True).stdout)
    assert web == pytest.approx([nod_offset(t) for t in (0, .1, .275, .5, .6)])
