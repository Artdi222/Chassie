"""Pure window placement and latest-generation avatar state."""
from dataclasses import dataclass
import ipaddress
import math
import random
from urllib.parse import urlsplit

from brain.emotion_parser import VALID_EMOTIONS


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


def bottom_right(screen: Rect, width: int = 360, height: int = 480, margin: int = 0) -> Rect:
    width = max(1, min(width, screen.width - 2 * margin))
    height = max(1, min(height, screen.height - 2 * margin))
    return Rect(screen.x + max(0, screen.width - width - margin),
                screen.y + max(0, screen.height - height - margin), width, height)


MIN_WINDOW = (200, 260)


def scaled_window(rect: Rect, factor: float, screen: Rect, margin: int = 0) -> Rect:
    """Scale the avatar window about its bottom-right corner, kept within the screen.

    The upper bound is the screen itself (the model fills whatever space it gets),
    so the avatar can be as large as the display allows.
    """
    aspect = rect.height / rect.width if rect.width else 4 / 3
    max_w, max_h = screen.width - 2 * margin, screen.height - 2 * margin
    width = max(MIN_WINDOW[0], round(rect.width * factor))
    width = min(width, max_w, round(max_h / aspect))
    height = max(MIN_WINDOW[1], round(width * aspect))
    right, bottom = rect.x + rect.width, rect.y + rect.height
    x = min(max(screen.x + margin, right - width), screen.x + screen.width - margin - width)
    y = min(max(screen.y + margin, bottom - height), screen.y + screen.height - margin - height)
    return Rect(x, y, width, height)


def fit_to_screens(rect: Rect, screens: list[Rect]) -> Rect:
    if not screens:
        raise ValueError("No display available for overlay")
    for screen in screens:
        if (screen.x <= rect.x and screen.y <= rect.y
                and rect.x + rect.width <= screen.x + screen.width
                and rect.y + rect.height <= screen.y + screen.height):
            right, bottom = screen.x + screen.width - rect.width, screen.y + screen.height - rect.height
            if right - rect.x <= 24 and bottom - rect.y <= 24:
                return Rect(right, bottom, rect.width, rect.height)  # Near the corner: sit in it (older 16 px margin).
            return rect
    return bottom_right(screens[0], rect.width, rect.height)


def validate_endpoint(endpoint: str) -> str:
    url = urlsplit(endpoint)
    try:
        loopback = url.hostname == 'localhost' or ipaddress.ip_address(url.hostname or '').is_loopback
    except ValueError:
        loopback = False
    if url.scheme != 'ws' or not loopback or url.username or url.password or url.fragment:
        raise ValueError("Overlay endpoint must be a local ws://localhost/ or loopback address")
    return endpoint


@dataclass
class OverlayState:
    emotion: str = 'neutral'
    variant: int = 0  # Which look of the emotion to show, when the model has several.
    mouth: float = 0.0
    generation: int = -1
    updated_at: float = 0.0
    status: str = 'disconnected'
    mic_enabled: bool | None = None
    gaze: tuple | None = None  # Owner's face position in the camera, [-1, 1] each axis.
    nod_at: float | None = None  # Last backchannel cue: nod while the owner talks.

    def receive(self, message: dict, now: float) -> bool:
        if message.get('type') == 'backchannel':
            self.nod_at = now
            return True
        if message.get('type') == 'settings':
            if isinstance(message.get('mic_enabled'), bool):
                self.mic_enabled = message['mic_enabled']
            return False
        if message.get('type') != 'avatar_state':
            return False
        generation, mouth = message.get('generation'), message.get('mouth')
        if (type(generation) is not int or generation < self.generation
                or type(mouth) not in (float, int) or not math.isfinite(mouth)
                or message.get('emotion') not in VALID_EMOTIONS):
            return False
        self.generation = generation
        if message['emotion'] != self.emotion:
            # A fresh look each time the feeling changes; steady while it stays the same.
            self.variant = random.randrange(1000)
        self.emotion = message['emotion']
        self.mouth = max(0.0, min(1.0, mouth))
        self.status = str(message.get('status', 'idle'))
        gaze = message.get('gaze')
        self.gaze = (tuple(max(-1.0, min(1.0, float(v))) for v in gaze)
                     if isinstance(gaze, list) and len(gaze) == 2
                     and all(type(v) in (float, int) and math.isfinite(v) for v in gaze) else None)
        self.updated_at = now
        return True

    def mouth_at(self, now: float) -> float:
        return self.mouth if now - self.updated_at <= 0.75 else 0.0

    def disconnected(self):
        self.emotion, self.mouth, self.generation = 'neutral', 0.0, -1
        self.status, self.mic_enabled, self.gaze = 'disconnected', None, None


MODEL_FRAMING = {'DeepSeek': (2.4, -1.25)}


@dataclass(frozen=True)
class Framing:
    """Model framing, independent of the desktop window's position and size."""
    zoom: float = 3.3
    vertical: float = -1.5

    @classmethod
    def for_model(cls, model_id):
        # DeepSeek-chan's canvas has more headroom above her head than Tian Muzi's.
        return cls(*MODEL_FRAMING.get(model_id, (2.4, -1.65)))

    def adjust(self, zoom: float = 0, vertical: float = 0):
        return Framing(max(1.0, min(6.0, self.zoom + zoom)),
                       max(-2.5, min(1.5, self.vertical + vertical)))

    @classmethod
    def from_settings(cls, data: dict):
        default = cls()
        zoom, vertical = data.get('zoom', default.zoom), data.get('vertical', default.vertical)
        if (type(zoom) not in (float, int) or type(vertical) not in (float, int)
                or not math.isfinite(zoom) or not math.isfinite(vertical)):
            return default
        return cls(zoom, vertical).adjust()


def left_arc(avatar: Rect, screen: Rect, diameter: int = 44) -> list[Rect]:
    """Compact, shallow curve following the left side of the character."""
    cx = avatar.x + avatar.width / 2 - avatar.width * .30 - 38
    cy = avatar.y + avatar.height * .52
    step = diameter + 12
    rects = [Rect(round(cx + 28 * (i / 2) ** 2 - diameter / 2),
                  round(cy + i * step - diameter / 2), diameter, diameter)
             for i in (-2, -1, 0, 1, 2)]
    left, top = min(r.x for r in rects), min(r.y for r in rects)
    right, bottom = max(r.x + diameter for r in rects), max(r.y + diameter for r in rects)
    dx = max(screen.x + 8 - left, min(0, screen.x + screen.width - 8 - right))
    dy = max(screen.y + 8 - top, min(0, screen.y + screen.height - 8 - bottom))
    return [Rect(r.x + dx, r.y + dy, diameter, diameter) for r in rects]
