"""Hand gestures from a model's own motion3 transitions (DeepSeek-chan: finger, hand on chest, grass).

The package ships "out" and "back" transitions per hand pose, all flagged Loop, so the SDK
motion player would repeat them and fight the reaction blending. Instead the curves are
evaluated here and written as parameters each frame: out, hold while the feeling lasts
(within limits), then back. A cooldown keeps her from waving on every sentence.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

MIN_HOLD, MAX_HOLD, COOLDOWN = 2.5, 7.0, 5.0


def parse_curves(data):
    """{parameter id: [(t0, v0, kind, points...)]} from motion3 JSON; kind 0 linear, 1 bezier, 2/3 stepped."""
    curves = {}
    for curve in data.get('Curves', []):
        if curve.get('Target') != 'Parameter':
            continue
        seg = curve['Segments']
        points, i = [], 2
        start = (seg[0], seg[1])
        while i < len(seg):
            kind = int(seg[i])
            if kind == 1:
                points.append((kind, start, (seg[i + 1], seg[i + 2]), (seg[i + 3], seg[i + 4]), (seg[i + 5], seg[i + 6])))
                start = (seg[i + 5], seg[i + 6]); i += 7
            else:
                points.append((kind, start, (seg[i + 1], seg[i + 2])))
                start = (seg[i + 1], seg[i + 2]); i += 3
        curves[curve['Id']] = (seg[0], seg[1], points)
    return curves


def _bezier(p0, p1, p2, p3, t):
    """Value at time t on a cubic bezier whose x is time (solved by bisection)."""
    lo, hi = 0.0, 1.0
    for _ in range(24):
        s = (lo + hi) / 2
        x = (1 - s) ** 3 * p0[0] + 3 * (1 - s) ** 2 * s * p1[0] + 3 * (1 - s) * s * s * p2[0] + s ** 3 * p3[0]
        lo, hi = (s, hi) if x < t else (lo, s)
    s = (lo + hi) / 2
    return (1 - s) ** 3 * p0[1] + 3 * (1 - s) ** 2 * s * p1[1] + 3 * (1 - s) * s * s * p2[1] + s ** 3 * p3[1]


def evaluate(curve, t):
    t0, v0, points = curve
    if t <= t0 or not points:
        return v0
    for kind, start, *rest in points:
        end = rest[-1]
        if t > end[0]:
            continue
        if kind == 0:
            span = end[0] - start[0]
            return start[1] + (end[1] - start[1]) * ((t - start[0]) / span if span else 1)
        if kind == 1:
            return _bezier(start, rest[0], rest[1], end, t)
        return start[1] if kind == 2 and t < end[0] else end[1]
    return points[-1][-1][1]


class Motion:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        self.duration = float(data['Meta']['Duration'])
        self.curves = parse_curves(data)

    def values(self, t):
        return {param: evaluate(curve, min(max(t, 0.0), self.duration)) for param, curve in self.curves.items()}


class GesturePlayer:
    """One hand pose at a time: out -> hold -> back -> cooldown."""

    def __init__(self, root, gestures, emotions, rest=None, rng=None):
        # gestures: {name: (out file, back file)}; emotions: {emotion: (gesture, chance)};
        # rest: parameters the transitions leave switched on, with their resting values.
        self.motions = {name: (Motion(Path(root) / out), Motion(Path(root) / back)) for name, (out, back) in gestures.items()}
        self.emotions = emotions
        self.rest = dict(rest or {})
        self.rng = rng or random.Random()
        self.current = None  # (gesture, phase, started)
        self.cooldown_until = 0.0
        self.emotion = None
        self.wanted = None

    def want(self, emotion, now):
        """Called every frame with the current emotion; picks a gesture when the feeling changes."""
        if emotion == self.emotion:
            return
        self.emotion = emotion
        choice = self.emotions.get(emotion)
        self.wanted = choice[0] if choice and now >= self.cooldown_until and self.rng.random() < choice[1] else None

    def step(self, now):
        """Parameter values to write this frame (empty when no gesture is active)."""
        if self.current is None:
            if self.wanted:
                self.current = (self.wanted, 'out', now)
                self.wanted = None
            else:
                return {}
        name, phase, started = self.current
        out, back = self.motions[name]
        t = now - started
        if phase == 'out':
            if t >= out.duration:
                self.current = (name, 'hold', now)
            return out.values(t)
        if phase == 'hold':
            keep = t < MIN_HOLD or (self.emotions.get(self.emotion, (None,))[0] == name and t < MAX_HOLD)
            if not keep or (self.wanted and self.wanted != name):
                self.current = (name, 'back', now)
            return out.values(out.duration)
        if t >= back.duration:
            self.current = None
            self.cooldown_until = now + COOLDOWN
            # Back at rest; the pose switch (Param56) returns to its default too.
            return {**back.values(back.duration), **self.rest}
        return back.values(t)
