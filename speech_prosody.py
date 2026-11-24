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

    def reset(self):
        """A new reply starts from its own mood, not the end of the last one."""
        self.previous = None

    def plan(self, text, emotion='neutral'):
        pitch, intonation, speed = EMOTIONS.get(emotion, EMOTIONS['neutral'])
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
