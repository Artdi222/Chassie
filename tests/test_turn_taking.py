import json

import numpy as np
import pytest

from brain.emotion_parser import quick_reaction
from speech.stt_engine import SpeechSegmenter
from test_backchannel import run
from test_orchestrator import app, playback_fixture  # noqa: F401  (fixtures)


def end_after_last_voice(segmenter, pattern):
    """Seconds of silence after the final speech before the utterance ended."""
    events = run(segmenter, pattern)
    voiced = sum(seconds for speech, seconds in pattern if speech)
    gaps = sum(seconds for speech, seconds in pattern[:-1] if not speech)
    end = next(t for kind, t in events if kind == 'utterance')
    return round(end - voiced - gaps, 2)


def test_untrained_segmenter_waits_the_configured_silence():
    assert end_after_last_voice(SpeechSegmenter(silence_duration=1.5), [(True, 1.2), (False, 3.0)]) == pytest.approx(1.5, abs=.06)


def test_short_pausers_are_answered_sooner_but_never_below_the_floor():
    segmenter = SpeechSegmenter(silence_duration=1.5)
    run(segmenter, [(True, .6), (False, .3)] * 12 + [(True, .6), (False, 2.0)])  # Learns ~0.3 s gaps.
    assert end_after_last_voice(segmenter, [(True, 1.2), (False, 3.0)]) == pytest.approx(.6, abs=.06)


def test_thinking_pausers_keep_their_patience():
    segmenter = SpeechSegmenter(silence_duration=1.5)
    run(segmenter, [(True, .6), (False, 1.0)] * 12 + [(True, .6), (False, 2.0)])
    assert end_after_last_voice(segmenter, [(True, 1.2), (False, 3.0)]) == pytest.approx(1.25, abs=.06)


def test_quick_reaction_reads_the_mood_of_the_message():
    cases = {'aku capek banget hari ini': 'concerned', 'kenapa aku capek terus?': 'concerned',
             'wkwk lucu banget': 'happy', 'makasih ya': 'happy', 'I passed the exam!': 'happy',
             'serius?? beneran?': 'surprised', 'wow no way': 'surprised',
             'kamu lagi ngapain?': 'curious', 'how does this work': 'curious',
             'oke': None, 'aku lagi ngoding': None}
    assert {text: quick_reaction(text) for text in cases} == cases


@pytest.mark.asyncio
async def test_face_reacts_before_the_model_answers(app):
    playback_fixture(app).first_release.set()
    seen = []
    async def stream(*a, **kw):
        seen.append(app._avatar_state['emotion'])
        yield '[happy] Okay.'
    app._hermes.stream_message = stream
    await app._run_turn({'text': 'aku capek banget hari ini', 'source': 'text'})
    assert seen == ['concerned']
