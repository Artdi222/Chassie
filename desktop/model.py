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


class CatalogModelDriver:
    def __init__(self, model, entry, clock=time.monotonic):
        self.model, self.entry = model, entry
        self.active = set()
        self.clock = clock
        self.follow = {}
        self.last = None

    def apply(self, selection, emotion):
        from avatar.catalog import active_files
        wanted = set(active_files(self.entry, selection, emotion))
        for name in self.active - wanted: self.model.RemoveExpression(name)
        for name in wanted - self.active: self.model.AddExpression(name)
        self.active = wanted

    def frame(self, mouth, pose=None, look=None):
        self.model.SetParameterValue('ParamMouthOpenY', mouth)
        # Parameters persist between frames in live2d-py, so an additive offset would
        # accumulate until the head pins at ±30°. Set the absolute pose each frame;
        # the SDK still adds breathing and gaze on top during Update().
        aliases = getattr(self.entry, 'aliases', None) or {}
        pose = dict(pose or {})
        now = self.clock()
        dt = min(max(now - self.last, 0.0), .1) if self.last is not None else 1 / 30
        self.last = now
        if 'ParamAngleX' in aliases:
            for param, (amplitude, period) in BREATH.items():
                pose[param] = pose.get(param, 0.0) + amplitude * math.sin(2 * math.pi * now / period)
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
