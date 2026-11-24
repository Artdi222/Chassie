"""Read-only model catalog and derived renderer manifests for local model packages."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import quote
from .interaction import interaction_settings
from .reactions import generated_reactions, expression_id

ROOT = Path(__file__).resolve().parents[1] / 'model'
# VTube Studio-style rigs take face tracking on custom inputs and let physics drive the
# standard ParamAngle*; writing ParamAngle* directly is overwritten every frame.
PARAM_ALIASES = {'DeepSeek': {'ParamAngleX': 'AngleX', 'ParamAngleY': 'AngleY', 'ParamAngleZ': 'AngleZ',
                              'ParamEyeLSmile': 'EyeSmile', 'ParamEyeRSmile': 'EyeSmile'}}
# VTS feeds these rigs' body physics from the face angles with smoothing (FaceAngle ->
# Position*), so the torso, hips and hair follow the head instead of standing still.
BODY_FOLLOW = {'DeepSeek': {'AngleX': 'PositionX', 'AngleY': 'PositionY', 'AngleZ': 'PositionZ'}}
DEFAULT_MODEL = 'Model_4'  # Tian Muzi stays the default; other local packages are opt-in
NAMES = {'Model_4': 'Tian Muzi', 'DeepSeek': 'DeepSeek-chan'}
LABELS = {
    '1 帽': ('Hat', 'accessory'), '2 手机': ('Phone', 'prop'),
    '3 麦克': ('Microphone', 'prop'), '4 手柄': ('Controller', 'prop'),
    '5 外套': ('Jacket', 'accessory'), '6 泪': ('Teary eyes', 'expression'),
    '7 害羞': ('Shy', 'expression'), '8 生气': ('Angry', 'expression'),
    '9 爱心眼': ('Heart eyes', 'expression'), '10 星星眼': ('Star eyes', 'expression'),
    '呆猫': ('Cat face', 'expression'), '呆猫眼珠摇晃': ('Moving cat eyes', 'expression'),
    '围裙': ('Apron', 'accessory'), '拍照': ('Photo pose', 'prop'),
    '拿笔': ('Hold a pen', 'prop'), '点一下': ('Touch pose', 'prop'),
    '猫咪滤镜': ('Cat filter', 'expression'), '眼镜': ('Glasses', 'accessory'),
    'XD': ('Laughing', 'expression'),
    'gonyogonyo': ('Mumbling', 'expression'),
    'jitome': ('Unimpressed', 'expression'),
    'kukkoro': ('Defeated', 'expression'),
    'oo': ('Open mouth', 'expression'),
    'perori': ('Tongue out', 'expression'),
    'highlight_onoff': ('Eye highlights', 'expression'),
    'costume_v0000': ('Outfit v0000', 'outfit'), 'costume_v0052': ('Outfit v0052', 'outfit'),
    'costume_v0101': ('Outfit v0101', 'outfit'),
    # DeepSeek-chan
    '体型1': ('Body size 1', 'outfit'), '体型2': ('Body size 2', 'outfit'), '默认体型': ('Default body', 'outfit'),
    '兔牙': ('Fang', 'expression'), '前倾': ('Lean forward', 'prop'), '加载': ('Loading', 'effect'),
    '单片眼镜': ('Monocle', 'accessory'), '圈圈眼': ('Swirl eyes', 'expression'), '尾巴开关': ('Tail', 'accessory'),
    '屑屑眼': ('Smug eyes', 'expression'), '流冷汗': ('Cold sweat', 'expression'), '流泪': ('Tears', 'expression'),
    '竖食指关': ('Finger down', 'prop'), '竖食指开': ('Finger up', 'prop'), '胸口衣服': ('Chest cloth', 'accessory'),
    '脱鞋': ('Shoes off', 'accessory'), '脸红': ('Blush', 'expression'), '裙子切换': ('Skirt switch', 'accessory'),
    '钢盆': ('Steel basin', 'prop'), '黑框眼镜': ('Black glasses', 'accessory'), '黑脸': ('Dark face', 'expression'),
    '＞＜': ('> < eyes', 'expression'), '爱心眼': ('Heart eyes', 'expression'),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


class ModelEntry:
    def __init__(self, model_id, path):
        self.id = model_id
        self.path = Path(path).resolve()
        self.root = self.path.parent
        self.data = read_json(self.path)
        self.assets = {}
        self.generated = {}
        self.expressions = []
        refs = self.data['FileReferences']
        for name in [refs['Moc'], *refs['Textures']]:
            self.asset(name)
        for key in ('Physics', 'Pose', 'DisplayInfo', 'UserData'):
            if refs.get(key): self.asset(refs[key])
        for motions in refs.get('Motions', {}).values():
            for motion in motions:
                for key in ('File', 'Sound'):
                    if motion.get(key): self.asset(motion[key])
        self.parameter_ids = set()
        self.head_parts = []
        if refs.get('DisplayInfo'):
            display = read_json(self.asset(refs['DisplayInfo']))
            self.parameter_ids = {p['Id'] for p in display.get('Parameters', [])}
            head_names = {'顔','顔輪郭','前髪','脸','前发','五官','头部','Head','Face','Front hair'}
            self.head_parts = [p['Id'] for p in display.get('Parts', []) if p.get('Name') in head_names]
        for file in sorted(self.root.rglob('*.exp3.json')):
            relative = file.relative_to(self.root).as_posix()
            params = read_json(self.asset(relative)).get('Parameters', [])
            if not params: continue
            stem = file.name.removesuffix('.exp3.json')
            label, kind = LABELS.get(stem, (stem.replace('_', ' '), 'effect' if stem.startswith('fx_') else 'expression'))
            self.expressions.append({'id': relative, 'name': label, 'original': stem, 'kind': kind, 'parameters': params})
        self.aliases={k:v for k,v in PARAM_ALIASES.get(self.id,{}).items() if v in self.parameter_ids}
        self.body_follow={k:v for k,v in BODY_FOLLOW.get(self.id,{}).items()
                          if k in self.parameter_ids and v in self.parameter_ids}
        self.generated=generated_reactions(self.parameter_ids,self.id)
        if self.generated:
            self.expressions.extend({'id':key,'name':Path(key).name.split('.')[0].title(),
                'original':Path(key).name.split('.')[0],'kind':'expression','generated':True,
                'parameters':value['Parameters']} for key,value in self.generated.items())

    def asset(self, relative):
        if not isinstance(relative, str) or '\\' in relative:
            raise ValueError('Invalid model asset reference')
        p = (self.root / relative).resolve()
        if not p.is_relative_to(self.root) or not p.is_file():
            raise ValueError(f'Model asset missing or outside package: {relative}')
        self.assets[relative] = p
        return p

    def manifest(self, reference):
        data = copy.deepcopy(self.data)
        refs = data['FileReferences']
        for key in ('Moc', 'Physics', 'Pose', 'DisplayInfo', 'UserData'):
            if refs.get(key): refs[key] = reference(refs[key])
        refs['Textures'] = [reference(p) for p in refs['Textures']]
        for motions in refs.get('Motions', {}).values():
            for motion in motions:
                for key in ('File', 'Sound'):
                    if motion.get(key): motion[key] = reference(motion[key])
        refs['Expressions'] = [{'Name': x['id'], 'File': reference(x['id'])} for x in self.expressions]
        groups = {g['Name']: g for g in data.get('Groups', [])}
        for name, ids in {'EyeBlink': ['ParamEyeLOpen', 'ParamEyeROpen'], 'LipSync': ['ParamMouthOpenY']}.items():
            if not groups.get(name, {}).get('Ids'):
                groups[name] = {'Target': 'Parameter', 'Name': name, 'Ids': [x for x in ids if x in self.parameter_ids]}
        data['Groups'] = list(groups.values())
        return data

    def public(self):
        return {'id': self.id, 'name': NAMES.get(self.id, self.id), 'source_name': self.path.stem.removesuffix('.model3'),
                'url': f'/api/models/{self.id}/model.json',
                'expressions': self.expressions, 'texture_count': len(self.data['FileReferences']['Textures']),
                'mouth': 'ParamMouthOpenY' in self.parameter_ids, 'head_parts': self.head_parts,
                'aliases': self.aliases}


class ModelCatalog:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.models = {}
        self.errors = []
        for path in sorted(self.root.rglob('*.model3.json')):
            relative = path.relative_to(self.root)
            if any(p.startswith('.') for p in relative.parts): continue
            model_id = relative.parts[0] if len(relative.parts) > 1 else relative.stem.removesuffix('.model3')
            if model_id in self.models:
                self.errors.append(f'{model_id}: more than one model manifest; select one package per folder')
                continue
            try:
                self.models[model_id] = ModelEntry(model_id, path)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.errors.append(f'{model_id}: {exc}')

    def get(self, model_id):
        if not isinstance(model_id, str) or model_id not in self.models:
            raise ValueError('Unknown model')
        return self.models[model_id]

    def public(self):
        return {'models': [m.public() for m in self.models.values()], 'errors': self.errors}

    def web_manifest(self, model_id):
        model = self.get(model_id)
        return model.manifest(lambda p: f'/api/models/{model_id}/assets/{quote(p, safe="/")}')


class ModelSelection:
    """Validated selections; expressions, persistent wardrobe and props are independent."""
    def __init__(self, catalog, path=None):
        self.catalog, self.path = catalog, Path(path) if path else None
        self.revision = 0
        self._interactions={}
        default=DEFAULT_MODEL if DEFAULT_MODEL in catalog.models else next(iter(catalog.models), None)
        self.state = {'model_id': default, 'expression': None, 'outfit': None,
                      'accessories': [], 'prop': None, 'effects': [], 'auto': True, 'mouth_preview': 0.0,
                      'interaction':interaction_settings()}
        if self.path and self.path.is_file():
            try:
                saved = read_json(self.path)
                preferences=saved.get('interaction_by_model',{})
                if isinstance(preferences,dict):
                    self._interactions={key:interaction_settings(value) for key,value in preferences.items() if key in catalog.models}
                self.change(saved, persist=False)
            except (OSError, ValueError, TypeError): pass

    def change(self, data, *, persist=True):
        model = self.catalog.get(data.get('model_id'))
        changed_model = model.id != self.state['model_id']
        candidate = dict(self.state) if not changed_model else {
            'model_id': model.id, 'expression': None, 'outfit': None, 'accessories': [],
            'prop': None, 'effects': [], 'auto': True, 'mouth_preview': 0.0,
            'interaction':interaction_settings(self._interactions.get(model.id))}
        allowed = {x['id']: x['kind'] for x in model.expressions}
        for field, kinds in {'expression': {'expression'}, 'outfit': {'outfit'}, 'prop': {'prop'}}.items():
            if field in data:
                value = data[field]
                if value is not None and (not isinstance(value, str) or allowed.get(value) not in kinds):
                    raise ValueError(f'This model does not provide the selected {field}')
                candidate[field] = value
        for field, kind in (('accessories', 'accessory'), ('effects', 'effect')):
            if field in data:
                value = data[field]
                if not isinstance(value, list) or len(value) > 32 or any(not isinstance(x, str) or allowed.get(x) != kind for x in value):
                    raise ValueError(f'Invalid {field} for this model')
                candidate[field] = sorted(set(value))
        if 'auto' in data:
            if type(data['auto']) is not bool: raise ValueError('auto must be boolean')
            candidate['auto'] = data['auto']
        if 'interaction' in data:
            if not isinstance(data['interaction'],dict):raise ValueError('Interaction settings must be an object')
            candidate['interaction']=interaction_settings({**candidate['interaction'],**data['interaction']})
        if 'mouth_preview' in data:
            value = data['mouth_preview']
            if type(value) not in (int, float) or not 0 <= value <= 1: raise ValueError('Mouth preview must be between 0 and 1')
            candidate['mouth_preview'] = value
        preferences={**self._interactions,model.id:dict(candidate['interaction'])}
        if self.path and persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            pending = self.path.with_suffix('.tmp')
            pending.write_text(json.dumps({**candidate, 'mouth_preview': 0.0,'interaction_by_model':preferences}, ensure_ascii=False), encoding='utf-8')
            pending.replace(self.path)
        self.state = candidate
        self._interactions=preferences
        self.revision += 1
        return self.payload()

    def payload(self):
        return {'type': 'model_state', 'revision': self.revision, **self.state}


def active_files(entry, selection, emotion='neutral'):
    names = [selection.get('outfit'), selection.get('prop'), *selection.get('accessories', []), *selection.get('effects', [])]
    if not selection.get('auto', True):
        names.append(selection.get('expression'))
    elif entry.generated:names.append(expression_id(emotion,entry.generated))
    return [x for x in names if x]
