import numpy as np
import pytest

from speech_pacing import SpeechPacing


def test_sentence_pause_accounts_for_existing_silence_and_synthesis_wait():
    pacing = SpeechPacing(1000)
    first = [np.r_[np.ones(100), np.zeros(100)]]
    second = [np.r_[np.zeros(50), np.ones(100)]]
    assert pacing.delay(second, now=0) == 0
    pacing.completed('Hello.', first, now=10)
    assert pacing.delay(second, now=10) == pytest.approx(.25)
    assert pacing.delay(second, now=10.2) == pytest.approx(.05)
    assert pacing.delay(second, now=11) == 0


def test_existing_tts_pause_is_never_removed_or_doubled():
    pacing = SpeechPacing(1000)
    pacing.completed('Hello.', [np.r_[np.ones(100), np.zeros(300)]], now=10)
    assert pacing.delay([np.r_[np.zeros(200), np.ones(100)]], now=10) == 0


@pytest.mark.parametrize('text,pause', [('Wait...', .55), ('Hello。', .4), ('A clause,', .18)])
def test_boundary_types_and_multi_block_silence(text, pause):
    pacing = SpeechPacing(1000)
    pacing.completed(text, [np.ones(100), np.zeros(50), np.zeros(50)], now=1)
    assert pacing.delay([np.zeros(50), np.ones(100)], now=1) == pytest.approx(pause - .15)


def test_edge_smoothing_preserves_length_tempo_and_middle_samples():
    pacing = SpeechPacing(1000)
    original = np.ones(100, dtype=np.float32)
    chunks = pacing.smooth([original[:4], original[4:96], original[96:]])
    audio = np.concatenate(chunks)
    assert len(audio) == len(original)
    assert audio[0] == audio[-1] == 0
    assert np.all(audio[8:-8] == 1)
    assert np.all(original == 1)


def test_smoothing_does_not_turn_a_naturally_quiet_tail_into_more_pause():
    pacing = SpeechPacing(1000)
    chunks = [np.r_[np.ones(100), np.zeros(100)]]
    pacing.completed('Done.', chunks, now=0)
    assert pacing.delay([np.ones(100)], now=0) == pytest.approx(.3)
