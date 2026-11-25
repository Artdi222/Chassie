import datetime as dt

import pytest

from brain.mood import Mood

NOON = dt.datetime(2026, 11, 25, 12, 0)


def mood(tmp_path):
    return Mood(tmp_path / 'inner-state.json')


def test_feelings_settle_back_to_her_baseline(tmp_path):
    m = mood(tmp_path)
    m.feel('down', 'lost a game', now=NOON)
    low = m.state(NOON)['valence']
    assert low < 0
    later = m.state(NOON + dt.timedelta(minutes=20))['valence']
    assert later == pytest.approx(.3 + (low - .3) / 2, abs=.01)  # Half-life of 20 minutes.
    assert m.state(NOON + dt.timedelta(hours=6))['valence'] == pytest.approx(.3, abs=.01)


def test_energy_follows_the_clock(tmp_path):
    m = mood(tmp_path)
    assert m.state(dt.datetime(2026, 11, 26, 2, 0))['energy'] == pytest.approx(.25, abs=.02)
    assert m.describe(dt.datetime(2026, 11, 26, 2, 0))['energy'] == 'sleepy'
    assert m.state(dt.datetime(2026, 11, 26, 14, 0))['energy'] == pytest.approx(.6, abs=.02)


def test_sulk_lifecycle_and_it_is_never_carried_into_a_new_session(tmp_path):
    m = mood(tmp_path)
    m.feel('sulky', 'called me noisy', now=NOON)
    assert m.describe(NOON)['sulking'] == {'about': 'called me noisy'}
    assert m.restraint(NOON) == 3
    assert 'sulking' in m.describe(NOON + dt.timedelta(minutes=15))
    assert 'sulking' not in m.describe(NOON + dt.timedelta(minutes=31))
    m.feel('sulky', 'called me noisy', now=NOON)
    m.feel('better', 'they apologized', now=NOON + dt.timedelta(minutes=1))
    assert 'sulking' not in m.describe(NOON + dt.timedelta(minutes=1))
    m.feel('sulky', 'called me noisy', now=NOON)
    reopened = mood(tmp_path)
    assert 'sulking' not in reopened.describe(NOON)
    assert reopened.state(NOON)['valence'] < .3  # The low mood itself still has to settle.


def test_closeness_grows_once_a_day(tmp_path):
    m = mood(tmp_path)
    start = m.state(NOON)['closeness']
    m.met(NOON)
    m.met(NOON + dt.timedelta(hours=2))
    once = m.state(NOON)['closeness']
    assert once == pytest.approx(start + (1 - start) * .03)
    m.met(NOON + dt.timedelta(days=1))
    assert mood(tmp_path).state(NOON)['closeness'] > once


def test_reactions_are_small_and_clamped(tmp_path):
    m = mood(tmp_path)
    for _ in range(100):
        m.react('excited', NOON)
    state = m.state(NOON)
    assert state['valence'] <= 1 and state['energy'] <= 1
    assert m.describe(NOON)['mood'] == 'cheerful'
    m.react('unknown-emotion', NOON)  # Ignored, not an error.


def test_prosody_and_initiative_follow_the_mood(tmp_path):
    cheerful, sulky = mood(tmp_path / 'a'), mood(tmp_path / 'b')
    for _ in range(10):
        cheerful.react('excited', NOON)
    sulky.feel('sulky', 'teased me', now=NOON)
    up, down = cheerful.prosody(NOON), sulky.prosody(NOON)
    assert up[0] > down[0] and up[1] > down[1] and up[2] > down[2]
    assert cheerful.restraint(NOON) == 1
    assert mood(tmp_path / 'c').restraint(dt.datetime(2026, 11, 26, 2, 0)) == 1.6


def test_feel_validates(tmp_path):
    with pytest.raises(ValueError):
        mood(tmp_path).feel('furious', 'x', now=NOON)


# --- Wiring ------------------------------------------------------------------------------

import json  # noqa: E402
import random  # noqa: E402

from brain.bilingual import BilingualChunker  # noqa: E402
from brain.initiative import InitiativeState, MODES  # noqa: E402
from speech.speech_prosody import ProsodyPlanner  # noqa: E402
from test_agenda import PAIR, agenda_turn  # noqa: E402
from test_initiative import observe  # noqa: E402
from test_orchestrator import app, playback_fixture  # noqa: F401,E402


def test_feel_lines_are_parsed_and_validated():
    assert BilingualChunker('en').feed('{"feel":"sulky","because":"called me noisy"}\n') == [
        ('feel', 'sulky', 'called me noisy')]
    assert BilingualChunker('en').feed('{"feel":"better"}\n') == [('feel', 'better', '')]
    for bad in ('{"feel":"furious"}\n', '{"feel":"down","because":"x","why":"y"}\n', '{"feel":1}\n'):
        with pytest.raises(ValueError):
            BilingualChunker('en').feed(bad)


@pytest.mark.asyncio
async def test_a_turn_changes_her_mood_and_the_context_carries_it(app):
    agenda_turn(app, '{"feel":"sulky","because":"called me noisy"}\n')
    await app._run_turn({'text': 'kamu berisik banget sih', 'source': 'text'})
    inner = json.loads(app._context_text())['inner_state']
    assert inner['sulking'] == {'about': 'called me noisy'} and inner['mood'] in ('a bit low', 'neutral')
    assert app._mood.state()['closeness'] > .1  # Met the owner today.


def test_planner_layers_the_mood_on_every_sentence():
    calm, lively = ProsodyPlanner(rng=random.Random(1)), ProsodyPlanner(rng=random.Random(1))
    lively.mood = (.02, 1.1, 1.05)
    a, b = calm.plan('そうだね。', 'neutral'), lively.plan('そうだね。', 'neutral')
    assert b['pitch'] > a['pitch'] and b['intonation'] > a['intonation'] and b['speed'] > a['speed']
    lively.reset()
    assert lively.mood == (.02, 1.1, 1.05)  # A new reply keeps her mood.


def test_restraint_stretches_every_wait():
    quiet = MODES['normal']['quiet']
    state = InitiativeState(last_activity=0)
    assert observe(state, quiet * 3 - 1, restraint=3) is None
    assert observe(state, quiet * 3, restraint=3)[0] == 'quiet'
