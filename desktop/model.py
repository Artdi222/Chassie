"""Derive a Cubism runtime manifest in cache without modifying original assets."""
import json
import os
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


class CatalogModelDriver:
    def __init__(self, model, entry):
        self.model, self.entry = model, entry
        self.active = set()

    def apply(self, selection, emotion):
        from avatar.catalog import active_files
        wanted = set(active_files(self.entry, selection, emotion))
        for name in self.active - wanted: self.model.RemoveExpression(name)
        for name in wanted - self.active: self.model.AddExpression(name)
        self.active = wanted

    def frame(self, mouth):
        self.model.SetParameterValue('ParamMouthOpenY', mouth)
        self.model.Update()
        self.model.Draw()
