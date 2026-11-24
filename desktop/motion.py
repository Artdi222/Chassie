"""Small procedural head motion layered on the SDK's own blink and breathing.

listening (the user is talking): a slight tilt, and a real nod at each pause (backchannel).
thinking: head tilted, eyes drifting up. speaking: faces the owner with small nods, almost no sway.
idle: very slow sway.
Values are additive offsets in degrees, eased between states so changes never snap.
"""
import math

POSES = {
    #            tilt Z, base Y, nod amp, nod period, sway amp, sway period
    'listening': (4.0, -2.0, 1.0, 1.6, 0.5, 5.0),  # Real nods come from backchannel cues.
    'thinking':  (-7.0, 6.0, 0.0, 1.0, 1.0, 6.0),
    'speaking':  (0.0, 0.0, 1.5, 0.9, 0.4, 3.2),
    'idle':      (0.0, 0.0, 0.0, 1.0, 1.2, 8.0),  # Stands upright; barely moves.
}


def target_pose(status, t):
    tilt, base_y, nod, nod_period, sway, sway_period = POSES.get(status, POSES['idle'])
    return {'ParamAngleZ': tilt + sway * math.sin(2 * math.pi * t / sway_period),
            'ParamAngleY': base_y + nod * max(0.0, math.sin(2 * math.pi * t / nod_period)) * -1,
            'ParamAngleX': sway * .6 * math.sin(2 * math.pi * t / (sway_period * 1.7))}


NOD_SECONDS = .55
NOD_DEGREES = 7.0


def nod_offset(since):
    """One soft downward nod: 0 at the start and end, deepest halfway."""
    if since is None or not 0 <= since < NOD_SECONDS: return 0.0
    return -NOD_DEGREES * math.sin(math.pi * since / NOD_SECONDS) ** 2


class HeadMotion:
    def __init__(self, available):
        self.params = [p for p in ('ParamAngleX', 'ParamAngleY', 'ParamAngleZ') if p in set(available)]
        self.current = {p: 0.0 for p in self.params}
        self.last = None

    def step(self, status, now, nod_at=None):
        dt = min(max(now - self.last, 0.0), .1) if self.last is not None else 1 / 30
        self.last = now
        ease = 1 - math.exp(-dt / .35)
        target = target_pose(status, now)
        for param in self.params:
            self.current[param] += (target[param] - self.current[param]) * ease
        pose = dict(self.current)
        if 'ParamAngleY' in pose:
            pose['ParamAngleY'] += nod_offset(now - nod_at if nod_at is not None else None)
        return pose
