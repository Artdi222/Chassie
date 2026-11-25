"""Chassie's inner state: how she feels, how awake she is, how close she is to the owner.

Kept in a small JSON file and written on every change, without any model call. Values settle
by the wall clock, so after the app was closed for a while she is back to her usual self. A
sulk is never carried into a new session. Rules for how she may show it live in the prompt.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from brain.reminders import write_json

BASELINE = .3                      # Her usual valence: mildly content.
HALF_LIFE = {'valence': 20 * 60, 'energy': 30 * 60, 'sulk': 10 * 60}  # Seconds.
SULK_MAX = dt.timedelta(minutes=30)
FEELINGS = {'sulky': -.25, 'down': -.35, 'better': .25}
# Small (valence, energy) nudge per spoken sentence of that emotion.
REACT = {'happy': (.04, .02), 'excited': (.06, .06), 'love': (.05, 0), 'teasing': (.03, .02),
         'curious': (.01, .02), 'surprised': (0, .04), 'shocked': (-.02, .05), 'flustered': (0, .03),
         'shy': (.01, 0), 'thinking': (0, 0), 'neutral': (0, 0), 'concerned': (-.03, 0),
         'sad': (-.06, -.02), 'defeated': (-.06, -.04), 'sleepy': (0, -.05), 'angry': (-.05, .03)}


def energy_target(hour):
    if hour < 6: return .25
    if hour < 9: return .45
    if hour >= 22: return .4
    return .6


def _clamp(value, low, high):
    return max(low, min(high, value))


def _settle(value, target, seconds, half_life):
    return target + (value - target) * .5 ** (max(0., seconds) / half_life)


class Mood:
    def __init__(self, path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        self.data = data if isinstance(data, dict) else {}
        if self.data.pop('sulk', None):
            write_json(self.path, self.data)  # A new session starts without yesterday's sulk.

    def state(self, now=None):
        """Current values after settling since the last change; reading never writes."""
        now = now or dt.datetime.now()
        target = energy_target(now.hour)
        updated = self.data.get('updated')
        if not updated:
            return {'valence': BASELINE, 'energy': target, 'sulk': None,
                    'closeness': self.data.get('closeness', .1), 'last_day': self.data.get('last_day')}
        seconds = (now - dt.datetime.fromisoformat(updated)).total_seconds()
        sulk = self.data.get('sulk')
        if sulk:
            level = _settle(sulk['level'], 0, seconds, HALF_LIFE['sulk'])
            since = dt.datetime.fromisoformat(sulk['since'])
            sulk = {**sulk, 'level': level} if level >= .2 and now - since <= SULK_MAX else None
        return {'valence': _settle(self.data['valence'], BASELINE, seconds, HALF_LIFE['valence']),
                'energy': _settle(self.data['energy'], target, seconds, HALF_LIFE['energy']),
                'sulk': sulk, 'closeness': self.data.get('closeness', .1), 'last_day': self.data.get('last_day')}

    def _save(self, state, now):
        state['valence'] = _clamp(state['valence'], -1, 1)
        state['energy'] = _clamp(state['energy'], 0, 1)
        self.data = {**{k: v for k, v in state.items() if v is not None},
                     'updated': now.isoformat(timespec='seconds')}
        write_json(self.path, self.data)

    def react(self, emotion, now=None):
        if emotion not in REACT: return
        now = now or dt.datetime.now()
        state = self.state(now)
        state['valence'] += REACT[emotion][0]
        state['energy'] += REACT[emotion][1]
        self._save(state, now)

    def feel(self, feeling, because='', now=None):
        if feeling not in FEELINGS:
            raise ValueError('Feeling must be sulky, down or better')
        now = now or dt.datetime.now()
        state = self.state(now)
        state['valence'] += FEELINGS[feeling]
        if feeling == 'sulky':
            state['sulk'] = {'level': 1.0, 'cause': ' '.join(str(because).split())[:120],
                             'since': now.isoformat(timespec='seconds')}
        elif feeling == 'better':
            state['sulk'] = None
        self._save(state, now)

    def met(self, now=None):
        """First owner turn of a day: she grows a little closer, slowly."""
        now = now or dt.datetime.now()
        state = self.state(now)
        if state.get('last_day') == now.date().isoformat(): return
        state['closeness'] += (1 - state['closeness']) * .03
        state['last_day'] = now.date().isoformat()
        self._save(state, now)

    def describe(self, now=None):
        state = self.state(now)
        v, e, c = state['valence'], state['energy'], state['closeness']
        result = {'mood': 'cheerful' if v > .5 else 'content' if v > .15 else 'neutral' if v > -.15
                  else 'a bit low' if v > -.5 else 'down',
                  'energy': 'energetic' if e > .7 else 'normal' if e > .4 else 'tired' if e > .3 else 'sleepy',
                  'closeness': 'new friends' if c < .2 else 'friends' if c < .5 else 'close friends' if c < .8
                  else 'very close'}
        if state['sulk']:
            result['sulking'] = {'about': state['sulk']['cause']}
        return result

    def prosody(self, now=None):
        """(pitch offset, intonation scale, speed scale) layered on each sentence's emotion."""
        state = self.state(now)
        v, e = state['valence'], state['energy'] - .6
        pitch, intonation, speed = .02 * v + .015 * e, 1 + .12 * e + .05 * v, 1 + .06 * e
        if state['sulk']:
            pitch, intonation, speed = pitch - .01, intonation * .9, speed * .97
        return round(pitch, 4), round(intonation, 4), round(speed, 4)

    def restraint(self, now=None):
        """How much longer than usual she waits before starting a chat herself."""
        state = self.state(now)
        if state['sulk']: return 3
        return 1.6 if state['energy'] < .35 else 1
