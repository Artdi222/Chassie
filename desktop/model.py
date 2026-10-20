"""Derive a Cubism runtime manifest in cache without modifying original assets."""
import copy
import json
import os
from pathlib import Path

from avatar import load_manifest, audit_assets


def prepare_model(model_dir: Path, cache_dir: Path) -> Path:
    model_dir, cache_dir = model_dir.resolve(), cache_dir.resolve()
    if cache_dir == model_dir or model_dir in cache_dir.parents:
        raise ValueError('Overlay cache must be outside the source model directory')
    if (model_dir / 'Model_1').is_dir(): model_dir = model_dir / 'Model_1'
    manifest = load_manifest()
    report = audit_assets(manifest, model_dir)
    if report['errors']:
        raise ValueError('Invalid model assets: ' + '; '.join(report['errors']))
    if cache_dir == model_dir or model_dir in cache_dir.parents:
        raise ValueError('Overlay cache must be outside the source model directory')
    source = model_dir / manifest.model_file
    data = copy.deepcopy(json.loads(source.read_text(encoding='utf-8')))

    def reference(filename):
        asset = (model_dir / filename).resolve()
        if not asset.is_relative_to(model_dir) or not asset.is_file():
            raise ValueError(f'Missing or external model asset: {filename}')
        return Path(os.path.relpath(asset, cache_dir)).as_posix()

    refs = data['FileReferences']
    for key in ('Moc', 'Physics', 'Pose', 'DisplayInfo', 'UserData'):
        if refs.get(key):
            refs[key] = reference(refs[key])
    refs['Textures'] = [reference(file) for file in refs['Textures']]
    for motions in refs.get('Motions', {}).values():
        for motion in motions:
            for key in ('File', 'Sound'):
                if motion.get(key):
                    motion[key] = reference(motion[key])
    refs['Expressions'] = [
        {'Name': filename, 'File': reference(asset['path'])}
        for filename, asset in sorted(report['assets'].items())
        if asset['parameters']  # Empty costume is deliberately not a selectable capability.
    ]
    bindings = {'EyeBlink': ['ParamEyeLOpen', 'ParamEyeROpen'], 'LipSync': ['ParamMouthOpenY']}
    groups = [g for g in data.get('Groups', []) if g.get('Name') not in bindings]
    groups.extend({'Target': 'Parameter', 'Name': name, 'Ids': ids} for name, ids in bindings.items())
    data['Groups'] = groups
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / manifest.model_file
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(data, indent=2), encoding='utf-8')
    pending.replace(path)
    return path


class ModelDriver:
    """Apply emotion/FX deltas through Cubism's real expression mixer."""
    def __init__(self, model):
        self.model = model
        self.manifest = load_manifest()
        self.active = set()
        self.emotion = 'neutral'

    def set_emotion(self, emotion: str):
        mapping = self.manifest.emotions.get(emotion)
        if mapping is None:
            return False
        wanted = set(mapping.files)
        for name in sorted(self.active - wanted):
            self.model.RemoveExpression(name)
        for name in mapping.files:
            if name not in self.active:
                self.model.AddExpression(name)
        self.active = wanted
        self.emotion = emotion
        return True

    def frame(self, mouth: float):
        self.model.SetParameterValue('ParamMouthOpenY', mouth)
        self.model.Update()
        self.model.Draw()


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
