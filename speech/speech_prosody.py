"""Lively delivery within one VOICEVOX style: per-sentence prosody that follows the line.

The voice never switches style or speaker (that sounded like a different person).
Instead each sentence gets small shifts in pitch, intonation range and tempo from its
emotion and shape (question, exclamation, trailing off), a little natural randomness,
and a contour: a gentle fall across the sentence, one emphasised phrase, and a rise at
the end of questions. Consecutive sentences are smoothed so the voice drifts, not jumps.
"""
from __future__ import annotations

import random
import re

# emotion: (pitch offset, intonation scale, speed multiplier). VOICEVOX pitch_scale is in
# log-F0 units: 0.03 is about half a semitone. Intonation 1.0 is the model's own range.
EMOTIONS = {
    'neutral':   (0.00, 1.12, 1.00),
    'happy':     (0.03, 1.30, 1.04),
    'excited':   (0.05, 1.42, 1.08),
    'love':      (0.03, 1.25, 0.97),
    'teasing':   (0.02, 1.35, 1.02),
    'curious':   (0.02, 1.25, 1.00),
    'surprised': (0.05, 1.45, 1.06),
    'shocked':   (0.06, 1.50, 1.08),
    'flustered': (0.05, 1.35, 1.10),
    'shy':       (0.01, 1.05, 0.95),
    'thinking':  (-0.01, 1.00, 0.94),
    'concerned': (-0.02, 0.98, 0.95),
    'sad':       (-0.04, 0.85, 0.90),
    'defeated':  (-0.05, 0.80, 0.90),
    'sleepy':    (-0.04, 0.80, 0.88),
    'angry':     (-0.01, 1.25, 1.05),
}
CARRY = 0.35  # Share of the previous sentence kept, so moods change gradually.
_QUESTION = re.compile(r'[？?][」』）)\s]*$')
_EXCLAIM = re.compile(r'[！!][」』）)\s]*$')
_TRAIL = re.compile(r'(?:…|‥|\.{2,}|・{2,}|[〜～ー])[」』）)\s]*$')


class ProsodyPlanner:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.previous = None
        self.mood = (0.0, 1.0, 1.0)  # (pitch offset, intonation scale, speed scale) from her inner state

    def reset(self):
        """A new reply starts from its own mood, not the end of the last one."""
        self.previous = None

    def plan(self, text, emotion='neutral'):
        pitch, intonation, speed = EMOTIONS.get(emotion, EMOTIONS['neutral'])
        pitch, intonation, speed = pitch + self.mood[0], intonation * self.mood[1], speed * self.mood[2]
        shape = 'question' if _QUESTION.search(text) else 'exclaim' if _EXCLAIM.search(text) else \
            'trail' if _TRAIL.search(text) else 'statement'
        if shape == 'question': intonation += .08
        elif shape == 'exclaim': intonation += .12; pitch += .01; speed *= 1.02
        elif shape == 'trail': speed *= .93; intonation -= .05
        # Nobody says two sentences exactly alike.
        pitch += self.rng.uniform(-.012, .012)
        intonation += self.rng.uniform(-.06, .06)
        speed *= self.rng.uniform(.98, 1.02)
        if self.previous:
            pitch = CARRY * self.previous['pitch'] + (1 - CARRY) * pitch
            intonation = CARRY * self.previous['intonation'] + (1 - CARRY) * intonation
            speed = CARRY * self.previous['speed'] + (1 - CARRY) * speed
        result = {'pitch': round(max(-.08, min(.08, pitch)), 4),
                  'intonation': round(max(.7, min(1.6, intonation)), 4),
                  'speed': round(max(.85, min(1.15, speed)), 4),
                  'shape': shape,
                  'emphasis': round(self.rng.random(), 4)}  # Which phrase carries the focus.
        self.previous = result
        return result


def apply_contour(accent_phrases, shape, emphasis):
    """Shape mora pitches in place: declination, one focused phrase, question rise, trailing fall.

    Works on voicevox_core AccentPhrase/Mora objects or plain dicts; unvoiced moras (pitch 0) stay 0.
    """
    def get(m, key): return m[key] if isinstance(m, dict) else getattr(m, key)
    def put(m, key, value):
        if isinstance(m, dict): m[key] = value
        else: setattr(m, key, value)
    phrases = [p for p in accent_phrases if get(p, 'moras')]
    count = len(phrases)
    if not count: return
    focus = min(count - 1, int(emphasis * count))
    for index, phrase in enumerate(phrases):
        # Start a little high and settle lower: about +-0.03 log-F0 across the sentence.
        offset = .03 * (1 - 2 * index / (count - 1)) if count > 1 else 0.0
        if index == focus and count > 1: offset += .035
        for mora in get(phrase, 'moras'):
            if get(mora, 'pitch') > 0: put(mora, 'pitch', get(mora, 'pitch') + offset)
    voiced = [m for m in get(phrases[-1], 'moras') if get(m, 'pitch') > 0]
    if shape == 'question' and not get(phrases[-1], 'is_interrogative'):
        for step, mora in enumerate(voiced[-2:], 1):
            put(mora, 'pitch', get(mora, 'pitch') + .07 * step)
    elif shape == 'trail':
        for step, mora in enumerate(voiced[-2:], 1):
            put(mora, 'pitch', get(mora, 'pitch') - .04 * step)


# Mouth openness per vowel (Japanese visemes); devoiced vowels (capital) barely open.
VOWEL_OPEN = {'a': 1.0, 'o': .78, 'e': .68, 'u': .5, 'i': .45, 'N': .18, 'cl': 0.0, 'pau': 0.0,
              'A': .25, 'I': .15, 'U': .15, 'E': .2, 'O': .2}
BILABIAL = {'m', 'b', 'p', 'my', 'by', 'py', 'f', 'w', 'v'}


def mouth_keyframes(query):
    """[time s, openness] keyframes following each mora of a VOICEVOX query, after speed scaling.

    Lips close for m/b/p and pauses, half-close on other consonants, and open per vowel.
    """
    def get(m, key, default=None):
        return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)
    speed = float(get(query, 'speed_scale') or 1.0)
    t = float(get(query, 'pre_phoneme_length') or 0.0) / speed
    frames = [[0.0, 0.0], [t, 0.0]]
    last = 0.0
    for phrase in get(query, 'accent_phrases') or []:
        moras = list(get(phrase, 'moras') or [])
        pause = get(phrase, 'pause_mora')
        for mora in moras + ([pause] if pause else []):
            consonant = get(mora, 'consonant')
            c_len = float(get(mora, 'consonant_length') or 0.0) / speed
            v_len = float(get(mora, 'vowel_length') or 0.0) / speed
            vowel = get(mora, 'vowel') or 'pau'
            if consonant and c_len > 0:
                closed = 0.0 if consonant in BILABIAL else last * .35
                frames.append([t + c_len * .6, closed])
            t += c_len
            value = VOWEL_OPEN.get(vowel, .5)
            if vowel in ('pau', 'cl'):
                frames.append([t + min(.05, v_len * .5), 0.0])
            else:
                frames.append([t + min(.045, v_len * .45), value])
                if v_len > .12:
                    frames.append([t + v_len - .04, value * .85])
            t += v_len
            last = value
    frames.append([t + .04, 0.0])
    return [[round(a, 4), round(b, 3)] for a, b in frames]
