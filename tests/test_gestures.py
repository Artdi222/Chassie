import json
import random

import pytest

from avatar.catalog import ModelCatalog
from desktop.attention import THINKING, Attention, direction, to_look
from desktop.gestures import COOLDOWN, MIN_HOLD, GesturePlayer, Motion, evaluate, parse_curves


def motion(path, segments, duration=1.0):
    path.write_text(json.dumps({'Meta': {'Duration': duration, 'Loop': True},
                                'Curves': [{'Target': 'Parameter', 'Id': 'Arm', 'Segments': segments}]}))
    return path.name


def test_curves_evaluate_linear_bezier_and_stepped():
    curves = parse_curves({'Curves': [
        {'Target': 'Parameter', 'Id': 'L', 'Segments': [0, 0, 0, 1, 10]},
        {'Target': 'Parameter', 'Id': 'B', 'Segments': [0, 0, 1, .33, 0, .66, 1, 1, 1]},
        {'Target': 'Parameter', 'Id': 'S', 'Segments': [0, 0, 2, .5, 1]},
        {'Target': 'PartOpacity', 'Id': 'P', 'Segments': [0, 1, 0, 1, 0]}]})
    assert set(curves) == {'L', 'B', 'S'}
    assert evaluate(curves['L'], .25) == pytest.approx(2.5) and evaluate(curves['L'], 5) == 10
    assert evaluate(curves['B'], .5) == pytest.approx(.5, abs=.02) and evaluate(curves['B'], .1) < .1
    assert evaluate(curves['S'], .4) == 0 and evaluate(curves['S'], .5) == 1


def test_gesture_goes_out_holds_returns_and_cools_down(tmp_path):
    out = motion(tmp_path / 'out.motion3.json', [0, 0, 0, 1, 1])
    back = motion(tmp_path / 'back.motion3.json', [0, 1, 0, 1, 0])
    player = GesturePlayer(tmp_path, {'finger': (out, back)}, {'thinking': ('finger', 1.0)},
                           rest={'Switch': 0.0}, rng=random.Random(0))
    assert player.step(0) == {}
    player.want('thinking', 0)
    assert player.step(0)['Arm'] == 0 and player.step(.5)['Arm'] == pytest.approx(.5)
    assert player.step(1.0)['Arm'] == 1  # Out finished: holding.
    player.want('happy', 1.2)
    assert player.step(1.2)['Arm'] == 1  # Still within the minimum hold.
    t = 1.0 + MIN_HOLD
    assert player.step(t)['Arm'] == 1 and player.current[1] == 'back'
    assert player.step(t + .5)['Arm'] == pytest.approx(.5)
    done = player.step(t + 1.0)
    assert done == {'Arm': 0, 'Switch': 0.0} and player.current is None
    player.want('thinking', t + 1.5)
    assert player.step(t + 1.5) == {}  # Cooling down: no new gesture yet.
    player.want('happy', t + 2); player.want('thinking', t + 1.0 + COOLDOWN + .1)
    assert player.step(t + 1.0 + COOLDOWN + .1) != {}


def test_attention_priorities_and_idle_glances():
    attention = Attention(rng=random.Random(1))
    assert attention.look('thinking', face=(.2, 0), chat=(-.5, 0), now=0) == THINKING
    assert attention.look('idle', face=(.2, 0), chat=(-.5, .1), now=0) == to_look((-.5, .1))
    assert attention.look('speaking', face=(.2, 0), now=0) == (.2, 0)
    assert attention.look('speaking', screen=(-.4, -.4), now=0) is None
    looks = [attention.look('idle', screen=(-.4, -.4), now=t / 2) for t in range(400)]
    glancing = [l for l in looks if l is not None]
    assert glancing and set(glancing) == {to_look((-.4, -.4))} and len(glancing) < len(looks) / 3
    assert direction((0, 0), (300, 400), 1000) == pytest.approx((.3, .4))
    assert direction((0, 0), (3000, 4000), 1000) == pytest.approx((.6, .8))


@pytest.mark.skipif('DeepSeek' not in ModelCatalog().models, reason='optional local DeepSeek-chan package')
def test_deepseek_package_has_all_hand_gestures():
    entry = ModelCatalog().get('DeepSeek')
    assert set(entry.gestures['gestures']) == {'finger', 'chest', 'grass'}
    finger = Motion(entry.root / entry.gestures['gestures']['finger'][0])
    assert finger.values(finger.duration)['Movement3'] == 1
    assert all('Movement3' not in [p['Id'] for p in v['Parameters']] for v in entry.generated.values())
