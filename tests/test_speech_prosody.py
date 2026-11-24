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


