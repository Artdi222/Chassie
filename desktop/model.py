"""Derive a Cubism runtime manifest in cache without modifying original assets."""
import json
import math
import os
import time
from pathlib import Path


def prepare_entry(entry, cache_dir):
    """Use one model's discovered assets for Native without editing its package."""
    cache_dir = Path(cache_dir).resolve()
    if cache_dir == entry.root or entry.root in cache_dir.parents:
        raise ValueError('Overlay cache must be outside original model assets')
    cache_dir.mkdir(parents=True, exist_ok=True)
    def reference(relative):
        if relative in entry.generated:
            path=cache_dir/entry.id/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(entry.generated[relative]),encoding='utf-8')
        else:path=entry.assets[relative]
        return os.path.relpath(path,cache_dir).replace(os.sep,'/')
    data = entry.manifest(reference)
    path = cache_dir / (entry.id + '.model3.json')
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


# The SDK's automatic breathing sways ParamAngle*/ParamBodyAngleX (peak x weight 0.5).
# Physics-driven rigs overwrite those outputs, so replay the same sway on their inputs.
BREATH = {'ParamAngleX': (7.5, 6.5345), 'ParamAngleY': (4.0, 3.5345), 'ParamAngleZ': (5.0, 5.5345)}
BODY_FOLLOW_SECONDS = .35  # VTS-like smoothing so the body trails the head.
# In conversation she holds still and faces the owner; the idle sway returns afterwards.
FOCUSED = {'speaking': .15, 'listening': .25}
FOCUS_SECONDS = .6


class CatalogModelDriver:
    def __init__(self, model, entry, clock=time.monotonic):
        self.model, self.entry = model, entry
        self.active = set()
        self.clock = clock
        self.follow = {}
        self.last = None
        self.sway = 1.0  # Eased breath sway scale: 1 idle, small while in conversation.

    def apply(self, selection, emotion):
        from avatar.catalog import active_files
        wanted = set(active_files(self.entry, selection, emotion))
        for name in self.active - wanted: self.model.RemoveExpression(name)
        for name in wanted - self.active: self.model.AddExpression(name)
        self.active = wanted

    def frame(self, mouth, pose=None, look=None, status=None):
        self.model.SetParameterValue('ParamMouthOpenY', mouth)
        # Parameters persist between frames in live2d-py, so an additive offset would
        # accumulate until the head pins at ±30°. Set the absolute pose each frame;
        # the SDK still adds breathing and gaze on top during Update().
        aliases = getattr(self.entry, 'aliases', None) or {}
        pose = dict(pose or {})
        now = self.clock()
        dt = min(max(now - self.last, 0.0), .1) if self.last is not None else 1 / 30
        self.last = now
        self.sway += (FOCUSED.get(status, 1.0) - self.sway) * (1 - math.exp(-dt / FOCUS_SECONDS))
        if 'ParamAngleX' in aliases:
            for param, (amplitude, period) in BREATH.items():
                # Keep a little vertical breathing; the side-to-side sway nearly stops.
                scale = .5 + .5 * self.sway if param == 'ParamAngleY' else self.sway
                pose[param] = pose.get(param, 0.0) + scale * amplitude * math.sin(2 * math.pi * now / period)
        if look and 'ParamAngleX' in aliases:
            # The SDK's Drag() writes ParamAngle*, which this rig's physics overwrites;
            # turn the head through the rig's own tracking inputs instead.
            pose['ParamAngleX'] = pose.get('ParamAngleX', 0.0) + 30 * look[0]
            pose['ParamAngleY'] = pose.get('ParamAngleY', 0.0) + 30 * look[1]
        values = {aliases.get(param, param): value for param, value in pose.items()}
        for param, value in values.items():
            self.model.SetParameterValue(param, value)
        ease = 1 - math.exp(-dt / BODY_FOLLOW_SECONDS)
        for source, target in (getattr(self.entry, 'body_follow', None) or {}).items():
            current = self.follow.get(target, 0.0)
            current += (values.get(source, 0.0) - current) * ease
            self.follow[target] = current
            self.model.SetParameterValue(target, current)
        self.model.Update()
        self.model.Draw()
