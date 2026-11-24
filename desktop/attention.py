"""Where Chassie looks when no cursor is near: a thought, the chat you type in, you, or your screen.

Returns a look target in the camera-face convention PointerInteraction already uses
(x mirrored: positive looks toward the viewer's left; y positive looks down).
"""
from __future__ import annotations

import math
import random

THINKING = (.35, -.55)  # Eyes up and to the side while she thinks.
GLANCE_EVERY = (18.0, 45.0)
GLANCE_FOR = (1.6, 3.2)


def direction(origin, point, reach):
    """Unit-ish screen direction from origin to point, saturating at `reach` pixels."""
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return 0.0, 0.0
    scale = min(1.0, length / reach) / length
    return dx * scale, dy * scale


def to_look(screen_dir):
    """Screen direction (right/down positive) to the pointer's look convention."""
    return (-screen_dir[0], screen_dir[1])


class Attention:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.next_glance = None
        self.glance_until = 0.0

    def look(self, status, *, face=None, chat=None, screen=None, now):
        """face: camera look (or None); chat / screen: screen directions to the chat panel / screen centre."""
        if status == 'thinking':
            return THINKING
        if chat is not None:
            return to_look(chat)  # The owner is typing to her: watch the message box.
        if face is not None:
            return face
        if status != 'idle' or screen is None:
            return None  # Talking without a visible face: straight ahead reads as eye contact.
        if self.next_glance is None:
            self.next_glance = now + self.rng.uniform(*GLANCE_EVERY)
        if now >= self.next_glance:
            self.glance_until = now + self.rng.uniform(*GLANCE_FOR)
            self.next_glance = self.glance_until + self.rng.uniform(*GLANCE_EVERY)
        return to_look(screen) if now < self.glance_until else None
