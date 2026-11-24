import random

from speech_prosody import ProsodyPlanner, apply_contour


def test_plan_follows_emotion_and_sentence_shape():
    planner = ProsodyPlanner(random.Random(1))
    sad = planner.plan('そうなんだ。', 'sad'); planner.reset()
    excited = planner.plan('すごい！', 'excited'); planner.reset()
    question = planner.plan('今日はどうだった？', 'curious'); planner.reset()
    trail = planner.plan('そうかな…', 'thinking')
    assert sad['pitch'] < 0 < excited['pitch'] and sad['intonation'] < excited['intonation']
    assert question['shape'] == 'question' and trail['shape'] == 'trail' and excited['shape'] == 'exclaim'
    assert trail['speed'] < 1


def test_consecutive_sentences_drift_instead_of_jumping():
    planner = ProsodyPlanner(random.Random(2))
    planner.plan('悲しいね。', 'sad')
    smoothed = planner.plan('やった！', 'excited')
    planner.reset()
    fresh = planner.plan('やった！', 'excited')
    assert smoothed['pitch'] < fresh['pitch']


def test_contour_falls_emphasises_and_rises_for_questions():
    phrases = [{'moras': [{'pitch': 5.8}, {'pitch': 0.0}], 'is_interrogative': False},
               {'moras': [{'pitch': 5.8}], 'is_interrogative': False},
               {'moras': [{'pitch': 5.8}, {'pitch': 5.8}], 'is_interrogative': False}]
    apply_contour(phrases, 'question', 0.0)
    assert phrases[0]['moras'][0]['pitch'] > phrases[1]['moras'][0]['pitch']
    assert phrases[0]['moras'][1]['pitch'] == 0.0  # Unvoiced moras stay unvoiced.
    last = [m['pitch'] for m in phrases[2]['moras']]
    assert last[1] > last[0] > 5.8 - .03



def test_mouth_keyframes_open_per_vowel_and_close_on_lips_and_pauses():
    from speech_prosody import mouth_keyframes
    from audio_player import keyframe_mouth
    query = {'speed_scale': 1.0, 'pre_phoneme_length': .1, 'accent_phrases': [
        {'moras': [{'consonant': 'm', 'consonant_length': .06, 'vowel': 'a', 'vowel_length': .15},
                   {'consonant': None, 'consonant_length': None, 'vowel': 'i', 'vowel_length': .1}],
         'pause_mora': {'vowel': 'pau', 'vowel_length': .2}}]}
    frames = mouth_keyframes(query)
    assert keyframe_mouth(frames, .05) == 0  # Silence before speech.
    assert keyframe_mouth(frames, .136) < .05  # Lips closed for "m".
    assert keyframe_mouth(frames, .22) > .9  # Wide "a".
    assert .3 < keyframe_mouth(frames, .36) < .6  # Narrow "i".
    assert keyframe_mouth(frames, .5) == 0  # Pause.
    faster = mouth_keyframes({**query, 'speed_scale': 2.0})
    assert faster[-1][0] < frames[-1][0]
